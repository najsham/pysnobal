# -*- coding: utf-8 -*-
"""
pysnobal: the Python wrapper of the Snobal libaries

snobal -z 2061 -t 60 -m 0.01 -s snow.properties.input 
-h inheight.input -p snobal.ppt.input 
-i snobal.data.input.short -o snobal.v1 -c

20160118 Scott Havens
"""

from pysnobal.c_snobal import c_snobal

import sys
import getopt
import numpy as np
import pandas as pd
import progressbar
import traceback


DEFAULT_MAX_Z_S_0 = 0.25
DEFAULT_MAX_H2O_VOL = 0.01

DATA_TSTEP = 0
NORMAL_TSTEP = 1
MEDIUM_TSTEP = 2
SMALL_TSTEP = 3

DEFAULT_NORMAL_THRESHOLD = 60.0
DEFAULT_MEDIUM_THRESHOLD = 10.0
DEFAULT_SMALL_THRESHOLD = 1.0
DEFAULT_MEDIUM_TSTEP = 15.0
DEFAULT_SMALL_TSTEP = 1.0

WHOLE_TSTEP = 0x1  # output when tstep is not divided
DIVIDED_TSTEP = 0x2  # output when timestep is divided


def hrs2min(x): return x * 60


def min2sec(x): return x * 60


C_TO_K = 273.16
FREEZE = C_TO_K


def SEC_TO_HR(x): return x / 3600.0

# Kelvin to Celcius


def K_TO_C(x): return x - FREEZE


def check_range(value, min_val, max_val, descrip):
    """
    Check the range of the value
    Args:
        value: value to check
        min_val: minimum value
        max_val: maximum value
        descrip: short description of input
    Returns:
        True if within range
    """
    if (value < min_val) or (value > max_val):
        raise ValueError("%s (%f) out of range: %f to %f",
                         descrip, value, min_val, max_val)
    return True


class PySnobal():

    def __init__(self):
        """
        PySnobal is a wrapper to the Snobal C code. Minmics
        how Snobal in IPW is ran with the same forcing files.
        """

        # Get the arguments
        self.get_args()

        # parse the options
        self.parseOptions()

        # open the input files
        self.open_files()

    def get_args(self):
        """
        Parse the input arguments, from getargs.c

        Args:
            argv: input arguments to pysnobal

        Returns:
            options: options structure with defaults if not set

            options = {
                z: site elevation (m),
                t: time steps: data [normal, [,medium [,small]]] (minutes),
                m: snowcover's maximum h2o content as volume ratio,
                d: maximum depth for active layer (m),
                s: snow properties input data file,
                h: measurement heights input data file,
                p: precipitation input data file,
                i: input data file,
                o: optional output data file,
                O: how often output records written (data, normal, all),
                c: continue run even when no snowcover,
                K: accept temperatures in degrees K,
                T: run timesteps' thresholds for a layer's mass (kg/m^2),
            }

        To-do: take all the rest of the defualt and check ranges for the
        input arguements, i.e. rewrite the rest of getargs.c
        """

        self.options = {
            'z': 2046.00463867,
            't': 60,
            'm': 0.01,
            'd': DEFAULT_MAX_Z_S_0,
            's': 'tests/test_data_point/gold.snow.properties.input',
            'h': 'tests/test_data_point/gold.inheight.input',
            'p': 'tests/test_data_point/gold.snobal.ppt.input',
            'i': 'tests/test_data_point/gold.snobal.data.input.short',
            'o': 'tests/test_data_point/snobal.pysnobal_c',
            'O': 'data',
            'c': True,
            'K': True,
            'T': DEFAULT_NORMAL_THRESHOLD,
        }

    def parseOptions(self):
        """
        Parse the options dict, set the default values if not specified
        May need to divide tstep_info and params up into different
        functions
        """

        # intialize the time step info
        # 0 : data timestep
        # 1 : normal run timestep
        # 2 : medium  "     "
        # 3 : small   "     "

        tstep_info = []
        for i in range(4):
            t = {'level': i, 'output': False, 'threshold': None,
                 'time_step': None, 'intervals': None}
            tstep_info.append(t)

        # The input data's time step must be between 1 minute and 6 hours.
        # If it is greater than 1 hour, it must be a multiple of 1 hour, e.g.
        # 2 hours, 3 hours, etc.

        data_tstep_min = self.options['t']
        check_range(data_tstep_min, 1.0, hrs2min(60), "input data's timestep")
        if ((data_tstep_min > 60) and (data_tstep_min % 60 != 0)):
            raise ValueError(
                "Data timestep > 60 min must be multiple of 60 min (whole hrs)")
        tstep_info[DATA_TSTEP]['time_step'] = min2sec(data_tstep_min)

        norm_tstep_min = 60.0
        tstep_info[NORMAL_TSTEP]['time_step'] = min2sec(norm_tstep_min)
        tstep_info[NORMAL_TSTEP]['intervals'] = int(
            data_tstep_min / norm_tstep_min)

        med_tstep_min = DEFAULT_MEDIUM_TSTEP
        tstep_info[MEDIUM_TSTEP]['time_step'] = min2sec(med_tstep_min)
        tstep_info[MEDIUM_TSTEP]['intervals'] = int(
            norm_tstep_min / med_tstep_min)

        small_tstep_min = DEFAULT_SMALL_TSTEP
        tstep_info[SMALL_TSTEP]['time_step'] = min2sec(small_tstep_min)
        tstep_info[SMALL_TSTEP]['intervals'] = int(
            med_tstep_min / small_tstep_min)

        # output
        if self.options['O'] == 'data':
            tstep_info[DATA_TSTEP]['output'] = DIVIDED_TSTEP
        elif self.options['O'] == 'normal':
            tstep_info[NORMAL_TSTEP]['output'] = WHOLE_TSTEP | DIVIDED_TSTEP
        elif self.options['O'] == 'all':
            tstep_info[NORMAL_TSTEP]['output'] = WHOLE_TSTEP
            tstep_info[MEDIUM_TSTEP]['output'] = WHOLE_TSTEP
            tstep_info[SMALL_TSTEP]['output'] = WHOLE_TSTEP
        else:
            tstep_info[DATA_TSTEP]['output'] = DIVIDED_TSTEP

    #     # mas thresholds for run timesteps
    #     threshold = DEFAULT_NORMAL_THRESHOLD
    #     tstep_info[NORMAL_TSTEP]['threshold'] = threshold
    #
    #     threshold = DEFAULT_MEDIUM_TSTEP
    #     tstep_info[MEDIUM_TSTEP]['threshold'] = threshold
    #
    #     threshold = DEFAULT_SMALL_TSTEP
    #     tstep_info[SMALL_TSTEP]['threshold'] = threshold

        # mass thresholds for run timesteps
        tstep_info[NORMAL_TSTEP]['threshold'] = DEFAULT_NORMAL_THRESHOLD
        tstep_info[MEDIUM_TSTEP]['threshold'] = DEFAULT_MEDIUM_THRESHOLD
        tstep_info[SMALL_TSTEP]['threshold'] = DEFAULT_SMALL_THRESHOLD

        # get the rest of the parameters
        params = {}

        params['elevation'] = self.options['z']
        params['data_tstep'] = data_tstep_min
        params['max_h2o_vol'] = self.options['m']
        params['max_z_s_0'] = self.options['d']
        params['sn_filename'] = self.options['s']
        params['mh_filename'] = self.options['h']
        params['in_filename'] = self.options['i']
        params['pr_filename'] = self.options['p']
        params['out_filename'] = self.options['o']
        params['out_file'] = open(params['out_filename'], 'w')
        params['stop_no_snow'] = self.options['c']
        params['temps_in_C'] = self.options['K']
        params['relative_heights'] = False

        self.params = params
        self.tstep_info = tstep_info

    def open_files(self):
        """
        Open and read the files
        """

        # read the snow properties record
        sn_prop = ['time_s', 'z_s', 'rho', 'T_s_0', 'T_s', 'h2o_sat']
        sn = pd.read_csv(self.params['sn_filename'], sep=' ',
                         header=None, names=sn_prop, index_col='time_s')

        # since I haven't seen multiple snow records before,
        # change the snow record to a dict and only keep the first
        # or initial value
        time_s = sn.iloc[0].name
        sn = sn.iloc[0].to_dict()
        sn['time_s'] = time_s

        # read the measurements height file
        ht_prop = ['time_z', 'z_u', 'z_t', 'z_0', 'z_g']
        # , index_col='time_z')
        mh = pd.read_csv(self.params['mh_filename'], sep=' ',
                         header=None, names=ht_prop)
        mh = mh.iloc[0].to_dict()

        # read the precipitation file
        ppt_prop = ['time_pp', 'm_pp', 'percent_snow', 'rho_snow', 'T_pp']
        pr = pd.read_csv(self.params['pr_filename'], sep=None, header=None,
                         names=ppt_prop, index_col='time_pp', engine='python')

        # read the input file
        in_prop = ['S_n', 'I_lw', 'T_a', 'e_a', 'u', 'T_g']
        force = pd.read_csv(self.params['in_filename'], sep=None,
                            header=None, names=in_prop, engine='python')

        # convert to Kelvin
        if self.params['temps_in_C']:
            sn['T_s_0'] += C_TO_K
            sn['T_s'] += C_TO_K
            pr.T_pp += C_TO_K
            force.T_a += C_TO_K
            force.T_g += C_TO_K

        # convert all to numpy arrays within the dict
        sn['z_0'] = mh['z_0']
        sn = self.dict2np(sn)
    #     mh = self.dict2np(mh)

        # check the ranges for the input values

        # check the precip, temp. cannot be below freezing if rain present
        # This is only present in Snobal and not iSnobal
        mass_rain = pr.m_pp * (1 - pr.percent_snow)
        pr.T_pp[(mass_rain > 0.0) & (pr.T_pp < FREEZE)] = FREEZE

        # combine the precip and force
        min_len = np.min([len(force), len(pr)])
        force = pd.concat([force, pr], axis=1)
        force = force[:min_len]

        # create the time steps for the forcing data
    #     time_f =

        self.sn = sn
        self.mh = mh
        self.force = force

    def dict2np(self, d):
        """
        The at least 2d is to trick snobal into thinking it's an ndarray
        """
        return {k: np.atleast_2d(np.array(v, dtype=float)) for k, v in d.items()}

    def initialize(self):
        """
        initialize
        """

        # create the self.output_rec with additional fields and fill
        # There are a lot of additional terms that the original self.output_rec does not
        # have due to the output function being outside the C code which doesn't
        # have access to those variables
        sz = self.sn['elevation'].shape
        flds = ['mask', 'elevation', 'z_0', 'rho', 'T_s_0', 'T_s_l', 'T_s',
                'cc_s_0', 'cc_s_l', 'cc_s', 'm_s', 'm_s_0', 'm_s_l', 'z_s', 'z_s_0', 'z_s_l',
                'h2o_sat', 'layer_count', 'h2o', 'h2o_max', 'h2o_vol', 'h2o_total',
                'R_n_bar', 'H_bar', 'L_v_E_bar', 'G_bar', 'G_0_bar',
                'M_bar', 'delta_Q_bar', 'delta_Q_0_bar', 'E_s_sum', 'melt_sum', 'ro_pred_sum',
                'current_time', 'time_since_out']
        s = {key: np.zeros(sz) for key in flds}  # the structure fields

        # go through each sn value and fill
        for key, val in self.sn.items():
            if key in flds:
                s[key] = val

        mh2 = self.dict2np(self.mh)
        for key, val in mh2.items():
            if key in flds:
                s[key] = val

        s['mask'] = np.ones(sz)
        self.output_rec = s

    def output_timestep(self):
        """
        Output the model results to a file
        ** 
        This is a departure from Snobal that can print out the
        sub-time steps, this will only print out on the data tstep
        (for now) 
        **

        """

        # write out to a file
        f = self.params['out_file']
        n = 0
        if f is not None:

            curr_time_hrs = SEC_TO_HR(self.output_rec['current_time'][n])

    #         # time
    #         f.write('%g,' % curr_time_hrs)
    #
    #         # energy budget terms
    #         f.write("%.1f,%.1f,%.1f,%.1f,%.1f,%.1f," % \
    #                 (self.output_rec['R_n_bar'][n], self.output_rec['H_bar'][n], self.output_rec['L_v_E_bar'][n], \
    #                 self.output_rec['G_bar'][n], self.output_rec['M_bar'][n], self.output_rec['delta_Q_bar'][n]))
    #
    #         # layer terms
    #         f.write("%.1f,%.1f," % \
    #                 (self.output_rec['G_0_bar'][n], self.output_rec['delta_Q_0_bar'][n]))
    #
    #         # heat storage and mass changes
    #         f.write("%.6e,%.6e,%.6e," % \
    #                 (self.output_rec['cc_s_0'][n], self.output_rec['cc_s_l'][n], self.output_rec['cc_s'][n]))
    #         f.write("%.5f,%.5f,%.5f," % \
    #                 (self.output_rec['E_s_sum'][n], self.output_rec['melt_sum'][n], self.output_rec['ro_pred_sum'][n]))
    #
    #         #             # runoff error if data included */
    #         #             if (ro_data)
    #         #                 fprintf(out, " %.1f",
    #         #                         (ro_pred_sum - (ro * time_since_out)))
    #
    #         # sno properties */
    #         f.write("%.3f,%.3f,%.3f,%.1f," % \
    #                 (self.output_rec['z_s_0'][n], self.output_rec['z_s_l'][n], self.output_rec['z_s'][n], self.output_rec['rho'][n]))
    #         f.write("%.1f,%.1f,%.1f,%.1f," % \
    #                 (self.output_rec['m_s_0'][n], self.output_rec['m_s_l'][n], self.output_rec['m_s'][n], self.output_rec['h2o'][n]))
    #         if self.params['temps_in_C']:
    #             f.write("%.2f,%.2f,%.2f\n" %
    #                     (K_TO_C(self.output_rec['T_s_0'][n]), K_TO_C(self.output_rec['T_s_l'][n]), K_TO_C(self.output_rec['T_s'][n])))
    #         else:
    #             f.write("%.2f,%.2f,%.2f\n" % \
    #                     (self.output_rec['T_s_0'][n], self.output_rec['T_s_l'][n], self.output_rec['T_s'][n]))

            # time
            f.write('%g,' % curr_time_hrs)

            # energy budget terms
            f.write("%.3f,%.3f,%.3f,%.3f,%.3f,%.3f," %
                    (self.output_rec['R_n_bar'][n], self.output_rec['H_bar'][n], self.output_rec['L_v_E_bar'][n],
                     self.output_rec['G_bar'][n], self.output_rec['M_bar'][n], self.output_rec['delta_Q_bar'][n]))

            # layer terms
            f.write("%.3f,%.3f," %
                    (self.output_rec['G_0_bar'][n], self.output_rec['delta_Q_0_bar'][n]))

            # heat storage and mass changes
            f.write("%.9e,%.9e,%.9e," %
                    (self.output_rec['cc_s_0'][n], self.output_rec['cc_s_l'][n], self.output_rec['cc_s'][n]))
            f.write("%.8f,%.8f,%.8f," %
                    (self.output_rec['E_s_sum'][n], self.output_rec['melt_sum'][n], self.output_rec['ro_pred_sum'][n]))

            #             # runoff error if data included */
            #             if (ro_data)
            #                 fprintf(out, " %.3f",
            #                         (ro_pred_sum - (ro * time_since_out)))

            # sno properties */
            f.write("%.6f,%.6f,%.6f,%.3f," %
                    (self.output_rec['z_s_0'][n], self.output_rec['z_s_l'][n], self.output_rec['z_s'][n], self.output_rec['rho'][n]))
            f.write("%.3f,%.3f,%.3f,%.3f," %
                    (self.output_rec['m_s_0'][n], self.output_rec['m_s_l'][n], self.output_rec['m_s'][n], self.output_rec['h2o'][n]))
            if self.params['temps_in_C']:
                f.write("%.5f,%.5f,%.5f\n" %
                        (K_TO_C(self.output_rec['T_s_0'][n]), K_TO_C(self.output_rec['T_s_l'][n]), K_TO_C(self.output_rec['T_s'][n])))
            else:
                f.write("%.5f,%.5f,%.5f\n" %
                        (self.output_rec['T_s_0'][n], self.output_rec['T_s_l'][n], self.output_rec['T_s'][n]))

            # reset the time since out
            self.output_rec['time_since_out'][n] = 0

    def run(self):
        """
        mimic the main.c from the Snobal model
        """

        # # parse the input arguments
        # options = get_args()
        # params, tstep_info = parseOptions(options)

        # # open the files and read in data
        # sn, mh, force = open_files(params)

        # initialize
        self.sn['elevation'] = np.atleast_2d(np.array(self.options['z']))
        self.initialize()

        # loop through the input
        # do_data_tstep needs two input records so only go
        # to the last record-1

        it = self.force[:-1].iterrows()
        index, input1 = next(it)    # this is the first input

        # add the precip to the data Series
    #     input1 = pd.concat([in1, pr.loc[index]])
        pbar = progressbar.ProgressBar(max_value=len(self.force)-1)
        j = 0

        data_tstep = self.tstep_info[0]['time_step']
        timeSinceOut = 0.0
        start_step = 0  # if restart then it would be higher if this were iSnobal
        step_time = start_step * data_tstep

        self.output_rec['current_time'] = step_time * \
            np.ones(self.output_rec['elevation'].shape)
        self.output_rec['time_since_out'] = timeSinceOut * \
            np.ones(self.output_rec['elevation'].shape)

        for index, input2 in it:

            # add the precip to the data Series
            #         input2 = pd.concat([in2, pr.loc[index]])

            first_step = 0
            if index == 1:
                first_step = 1

            try:
                # call do_data_tstep()
                c_snobal.do_tstep_grid(self.dict2np(input1.to_dict()), self.dict2np(
                    input2.to_dict()), self.output_rec, self.tstep_info, self.mh, self.params, first_step)
    #             s.do_data_tstep(self.dict2np(input1.to_dict()), self.dict2np(input2.to_dict()))

                # output the results
                self.output_timestep()

            except Exception as e:
                traceback.print_exc()
                print('pysnobal error on time step %f' %
                      (self.output_rec['current_time'][0, 0]/3600.0))
                print(e)
                return False
    #

            # input2 becomes input1
            input1 = input2.copy()

            j += 1
            if j % 10 == 0:
                pbar.update(j)

        pbar.finish()

        # output
        self.params['out_file'].close()

        return True
