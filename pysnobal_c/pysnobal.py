# -*- coding: utf-8 -*-
"""
pysnobal: the Python wrapper of the Snobal libaries

snobal -z 2061 -t 60 -m 0.01 -s snow.properties.input 
-h inheight.input -p snobal.ppt.input 
-i snobal.data.input.short -o snobal.v1 -c

20160118 Scott Havens
"""

import snobal

import sys, getopt
import numpy as np
import pandas as pd
import progressbar
import traceback

# class MyApplication():
#     # My code here
#     pass

DEFAULT_MAX_Z_S_0 = 0.25
DEFAULT_MAX_H2O_VOL = 0.01

DATA_TSTEP = 0
NORMAL_TSTEP = 1
MEDIUM_TSTEP = 2
SMALL_TSTEP = 3

DEFAULT_NORMAL_THRESHOLD = 60.0
DEFAULT_MEDIUM_TSTEP = 15.0
DEFAULT_SMALL_TSTEP = 1.0

WHOLE_TSTEP = 0x1 # output when tstep is not divided
DIVIDED_TSTEP = 0x2  # output when timestep is divided

hrs2min = lambda x: x * 60
min2sec = lambda x: x * 60
C_TO_K = 273.16
FREEZE = C_TO_K


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
        raise ValueError("%s (%f) out of range: %f to %f", descrip, value, min_val, max_val);
    return True

def get_args(argv):
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

#     inputfile = ''
#     outputfile = ''
#     
#     try:
#         opts, args = getopt.getopt(argv, "hi:o:", ["ifile=", "ofile="])
#     except getopt.GetoptError:
#         print 'test.py -i <inputfile> -o <outputfile>'
#         sys.exit(2)
#     
#     for opt, arg in opts:
#         if opt == '-h':
#             print 'test.py -i <inputfile> -o <outputfile>'
#             sys.exit()
#         elif opt in ("-i", "--ifile"):
#             inputfile = arg
#         elif opt in ("-o", "--ofile"):
#             outputfile = arg
#     
#     print 'Input file is "', inputfile
#     print 'Output file is "', outputfile

    options = {
        'z': 2061,
        't': 60,
        'm': 0.01,
        'd': DEFAULT_MAX_Z_S_0,
        's': '../test_data_spatial/point/snow.properties.input',
        'h': '../test_data_spatial/point/inheight.input',
        'p': '../test_data_spatial/point/snobal.ppt.input',
        'i': '../test_data_spatial/point/snobal.input',
        'o': '../test_data_spatial/point/snobal.exact',
        'O': 'all',
        'c': True,
        'K': True,
        'T': DEFAULT_NORMAL_THRESHOLD,
    }
    
    return options

def parseOptions(options):
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
        t = {}
        t['level'] = i;
        t['output'] = False;
        tstep_info.append(t)
    

    # The input data's time step must be between 1 minute and 6 hours.
    # If it is greater than 1 hour, it must be a multiple of 1 hour, e.g.
    # 2 hours, 3 hours, etc.
     
    data_tstep_min = options['t'];
    check_range (data_tstep_min, 1.0, hrs2min(60),"input data's timestep")
    if ((data_tstep_min > 60) and (data_tstep_min % 60 != 0)):
        raise ValueError("Data timestep > 60 min must be multiple of 60 min (whole hrs)")
    tstep_info[DATA_TSTEP]['time_step'] = min2sec(data_tstep_min);
    
    norm_tstep_min = 60.0
    tstep_info[NORMAL_TSTEP]['time_step'] = min2sec(norm_tstep_min)
    tstep_info[NORMAL_TSTEP]['intervals'] = int(data_tstep_min / norm_tstep_min)
    
    med_tstep_min = DEFAULT_MEDIUM_TSTEP
    tstep_info[MEDIUM_TSTEP]['time_step'] = min2sec(med_tstep_min)
    tstep_info[MEDIUM_TSTEP]['intervals'] = int(norm_tstep_min / med_tstep_min)
    
    small_tstep_min = DEFAULT_SMALL_TSTEP
    tstep_info[SMALL_TSTEP]['time_step'] = min2sec(small_tstep_min)
    tstep_info[SMALL_TSTEP]['intervals'] = int(med_tstep_min / small_tstep_min)
    
    # output
    if options['O'] == 'data':
        tstep_info[DATA_TSTEP]['output'] = DIVIDED_TSTEP
    elif options['O'] == 'normal':
        tstep_info[NORMAL_TSTEP]['output'] = WHOLE_TSTEP | DIVIDED_TSTEP
    elif options['O'] == 'all':
        tstep_info[NORMAL_TSTEP]['output'] = WHOLE_TSTEP
        tstep_info[MEDIUM_TSTEP]['output'] = WHOLE_TSTEP
        tstep_info[SMALL_TSTEP]['output'] = WHOLE_TSTEP
    else:
        tstep_info[DATA_TSTEP]['output'] = DIVIDED_TSTEP
    
    # mas thresholds for run timesteps
    threshold = DEFAULT_NORMAL_THRESHOLD
    tstep_info[NORMAL_TSTEP]['threshold'] = threshold
    
    threshold = DEFAULT_MEDIUM_TSTEP
    tstep_info[MEDIUM_TSTEP]['threshold'] = threshold
    
    threshold = DEFAULT_SMALL_TSTEP
    tstep_info[SMALL_TSTEP]['threshold'] = threshold
    
    
    # get the rest of the parameters
    params = {}
    
    params['elevation'] = options['z']
    params['data_tstep'] = data_tstep_min
    params['max_h2o_vol'] = options['m']
    params['max_z_s_0'] = options['d']
    params['sn_filename'] = options['s']
    params['mh_filename'] = options['h']
    params['in_filename'] = options['i']
    params['pr_filename'] = options['p']
    params['out_filename'] = options['o']
    params['out_file'] = open(params['out_filename'], 'w')
    params['stop_no_snow'] = options['c']
    params['temps_in_C'] = options['K']
    params['relative_heights'] = False

    return params, tstep_info


def open_files(params):
    """
    Open and read the files
    """
    
    # read the snow properties record
    sn_prop = ['time_s', 'z_s', 'rho', 'T_s_0', 'T_s', 'h2o_sat']
    sn = pd.read_csv(params['sn_filename'], sep=' ', header=None, names=sn_prop, index_col='time_s')
        
    # since I haven't seen multiple snow records before,
    # change the snow record to a dict and only keep the first 
    # or initial value
    time_s = sn.iloc[0].name
    sn = sn.iloc[0].to_dict()
    sn['time_s'] = time_s
        
    # read the measurements height file
    ht_prop = ['time_z', 'z_u', 'z_t', 'z_0', 'z_g']
    mh = pd.read_csv(params['mh_filename'], sep=' ', header=None, names=ht_prop) #, index_col='time_z')
    mh = mh.iloc[0].to_dict()
    
    
    # read the precipitation file
    ppt_prop = ['time_pp', 'm_pp', 'percent_snow', 'rho_snow', 'T_pp']
    pr = pd.read_csv(params['pr_filename'], sep=None, header=None, names=ppt_prop, index_col='time_pp', engine='python')
    
    # read the input file
    in_prop = ['S_n', 'I_lw', 'T_a', 'e_a', 'u', 'T_g']
    force = pd.read_csv(params['in_filename'], sep=None, header=None, names=in_prop, engine='python')
    
    # convert to Kelvin
    if params['temps_in_C']:
        sn['T_s_0'] += C_TO_K
        sn['T_s'] += C_TO_K
        pr.T_pp += C_TO_K
        force.T_a += C_TO_K
        force.T_g += C_TO_K
        
    
    # convert all to numpy arrays within the dict
    sn['z_0'] = mh['z_0']
    sn = dict2np(sn)
    mh = dict2np(mh)
                   
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
    
    return sn, mh, force

def dict2np(d):
    """
    The at least 2d is to trick snobal into thinking it's an ndarray
    """
    return {k: np.atleast_2d(np.array(v, dtype=float)) for k,v in d.items()}


def initialize(params, tstep_info, sn, mh):
    """
    initialize
    """
    
    # create the OUTPUT_REC with additional fields and fill
    sz = sn['elevation'].shape
    flds = ['masked', 'elevation', 'z_0', 'z_s', 'rho', 'T_s_0', 'T_s_l', 'T_s', \
            'h2o_sat', 'layer_count', 'R_n_bar', 'H_bar', 'L_v_E_bar', 'G_bar', \
            'M_bar', 'delta_Q_bar', 'E_s_sum', 'melt_sum', 'ro_pred_sum']
    s = {key: np.zeros(sz) for key in flds} # the structure fields
    
    # go through each sn value and fill
    for key, val in sn.items():
        if key in flds:
            s[key] = val
            
    for key, val in mh.items():
        if key in flds:
            s[key] = val
        
    return s
    
    
    
def run(data):
    """
    Acutally run the model
    """

#@profile
def main(argv):
    """
    mimic the main.c from the Snobal model
    """
    
    # parse the input arguments
    options = get_args(argv)
    params, tstep_info = parseOptions(options)

    # open the files and read in data
    sn, mh, force = open_files(params)
    
    # initialize
    sn['elevation'] = np.atleast_2d(np.array(options['z']))
    output_rec = initialize(params, tstep_info, sn, mh)
    
    # loop through the input
    # do_data_tstep needs two input records so only go 
    # to the last record-1
    
    it = force[:-1].iterrows()
    index, input1 = next(it)    # this is the first input
    
    # add the precip to the data Series
#     input1 = pd.concat([in1, pr.loc[index]])
    pbar = progressbar.ProgressBar(max_value=len(force)-1)
    j = 0
    for index,input2 in it:
    
        # add the precip to the data Series
#         input2 = pd.concat([in2, pr.loc[index]])
    
        try:
            # call do_data_tstep()
            snobal.do_tstep(dict2np(input1.to_dict()), dict2np(input2.to_dict()), output_rec, mh)
#             s.do_data_tstep(dict2np(input1.to_dict()), dict2np(input2.to_dict()))
        
        except Exception, e:
            traceback.print_exc()
            print('pysnobal error on time step %f' % (output_rec.current_time[0,0]/3600.0))
            print(e)
            return
#             
        
        # input2 becomes input1
        input1 = input2.copy()
        
        j += 1
        pbar.update(j)
        
    pbar.finish()
    
    
    
    
    # output
    params['out_file'].close()
#     app = MyApplication()
#     app.run()




if __name__ == "__main__":
    main(sys.argv[1:])

    
    
