/*
 * call_snobal.c takes input from a Python function and calls all the necessary C functions
 */

#include <stdio.h>

#include <math.h>
#include <string.h>
#include <omp.h>
#include "snobal.h"
#include "envphys.h"
#include "pysnobal.h"

int call_snobal (
		int N,
		int nthreads,
		int first_step,
		TSTEP_REC tstep_info[4],
		OUTPUT_REC** output_rec,
		INPUT_REC_ARR* input1,
		INPUT_REC_ARR* input2,
		PARAMS params
)
{
	int n, masked;
	double current_time, time_since_out;
	double data_tstep;

	// Some debuging stuff
	//	printf("%i\n", tstep_info[1].level);
	//		printf("%f - %f - %f - %f - %f - %f\n", input1->S_n[0], input1->I_lw[0], input1->T_a[0], input1->e_a[0], input1->u[0], input1->T_g[0]);
	//	printf ("%i -- %f\n", N, output_rec[0]->elevation);

	/* set threads */
	if (nthreads != 1) {
		omp_set_num_threads(nthreads); 	// Use N threads for all consecutive parallel regions
	}

	// for some reason, C compiler doen't let you threadprivate the tstep since it's already created.
	// Therefore, we need to create a pointer to it, apply threadprivate, then copy in the data from the input
	//	static TSTEP_REC *tstep_info;
	//#pragma omp threadprivate(tstep_info)
	//	tstep_info = tstep;

	data_tstep = tstep_info[DATA_TSTEP].time_step;

	// pull out the parameters
	z_u = params.z_u;
	z_T = params.z_T;
	z_g = params.z_g;
	relative_hts = params.relative_heights;
	max_z_s_0 = params.max_z_s_0;
	max_h2o_vol = params.max_h2o_vol;

//	printf("%i -- %i -- %f -- %f\n", tstep_info[0].level, tstep_info[0].time_step, tstep_info[0].intervals, tstep_info[0].threshold);
//	printf("%i -- %i -- %f -- %f\n", tstep_info[1].level, tstep_info[1].time_step, tstep_info[1].intervals, tstep_info[1].threshold);
//	printf("%i -- %i -- %f -- %f\n", tstep_info[2].level, tstep_info[2].time_step, tstep_info[2].intervals, tstep_info[2].threshold);
//	printf("%i -- %i -- %f -- %f\n", tstep_info[3].level, tstep_info[3].time_step, tstep_info[3].intervals, tstep_info[3].threshold);


	//#pragma omp parallel shared(output_rec, input1, input2, first_step)\
	//		private(n) \
	//		copyin(tstep_info, z_u, z_T, z_g, relative_hts, max_z_s_0, max_h2o_vol)
	//	{
	//#pragma omp for schedule(dynamic, 100)
	for (n = 0; n < N; n++) {

		if (output_rec[n]->masked == 1) {

			/* initialize some global variables for
			   'snobal' library for each pass since
			   the routine 'do_data_tstep' modifies them */

			current_time = output_rec[n]->current_time;
			time_since_out = output_rec[n]->time_since_out;

			// get the input records
			input_rec1.I_lw = input1->I_lw[n];
			input_rec1.T_a  = input1->T_a[n];
			input_rec1.e_a  = input1->e_a[n];
			input_rec1.u    = input1->u[n];
			input_rec1.T_g  = input1->T_g[n];
			input_rec1.S_n  = input1->S_n[n];

			input_rec2.I_lw = input2->I_lw[n];
			input_rec2.T_a  = input2->T_a[n];
			input_rec2.e_a  = input2->e_a[n];
			input_rec2.u    = input2->u[n];
			input_rec2.T_g  = input2->T_g[n];
			input_rec2.S_n  = input2->S_n[n];


			// precip inputs
			m_pp         = input1->m_pp[n];
			percent_snow = input1->percent_snow[n];
			rho_snow     = input1->rho_snow[n];
			T_pp         = input1->T_pp[n];

			precip_now = 0;
			if (m_pp > 0)
				precip_now = 1;


			/* extract data from I/O buffers */
			double elevation    = output_rec[n]->elevation;
			z_0	     	 = output_rec[n]->z_0;
			z_s          = output_rec[n]->z_s;
			rho	     	 = output_rec[n]->rho;
			T_s_0	     = output_rec[n]->T_s_0;
			T_s_l	     = output_rec[n]->T_s_l;
			T_s	         = output_rec[n]->T_s;
			h2o_sat	     = output_rec[n]->h2o_sat;
			//				layer_count  = output_rec[n]->layer_count;

			//				R_n_bar	     = output_rec[n]->R_n_bar;
			//				H_bar	     = output_rec[n]->H_bar;
			//				L_v_E_bar    = output_rec[n]->L_v_E_bar;
			//				G_bar	     = output_rec[n]->G_bar;
			//				M_bar	     = output_rec[n]->M_bar;
			//				delta_Q_bar  = output_rec[n]->delta_Q_bar;
			//				E_s_sum      = output_rec[n]->E_s_sum;
			//				melt_sum     = output_rec[n]->melt_sum;
			//				ro_pred_sum  = output_rec[n]->ro_pred_sum;

			/* establish conditions for snowpack */

			//				if (first_step == 1) {
			init_snow();
			//				R_n_bar	     = 0.0;
			//				H_bar	     = 0.0;
			//				L_v_E_bar    = 0.0;
			//				G_bar	     = 0.0;
			//				M_bar	     = 0.0;
			//				delta_Q_bar  = 0.0;
			//				E_s_sum      = 0.0;
			//				melt_sum     = 0.0;
			//				ro_pred_sum  = 0.0;
			//				}

			//				printf("Mass %f\n", m_s);

			/* set air pressure from site elev */

			P_a = HYSTAT(SEA_LEVEL, STD_AIRTMP, STD_LAPSE, (output_rec[n]->elevation / 1000.0),
					GRAVITY, MOL_AIR);

			/* run model on data for this pixel */

			if (! do_data_tstep())
				fprintf(stderr, "Error at pixel %i", n);

			/* assign data to output buffers */
			current_time += data_tstep;
			output_rec[n]->current_time = current_time;
			output_rec[n]->time_since_out = time_since_out;

			//			output_rec[n]->elevation = elevation;
			output_rec[n]->z_0 = z_0;
			output_rec[n]->rho = rho;
			output_rec[n]->T_s_0 = T_s_0;
			output_rec[n]->T_s_l = T_s_l;
			output_rec[n]->T_s = T_s;
			output_rec[n]->h2o_sat = h2o_sat;
			output_rec[n]->h2o_max = h2o_max;
			output_rec[n]->h2o = h2o;
			output_rec[n]->layer_count = layer_count;
			output_rec[n]->cc_s_0 = cc_s_0;
			output_rec[n]->cc_s_l = cc_s_l;
			output_rec[n]->cc_s = cc_s;
			output_rec[n]->m_s_0 = m_s_0;
			output_rec[n]->m_s_l = m_s_l;
			output_rec[n]->m_s = m_s;
			output_rec[n]->z_s_0 = z_s_0;
			output_rec[n]->z_s_l = z_s_l;
			output_rec[n]->z_s = z_s;

			//				output_rec[n]->R_n_bar = R_n_bar;
			//				output_rec[n]->H_bar = H_bar;
			//				output_rec[n]->L_v_E_bar = L_v_E_bar;
			//				output_rec[n]->G_bar = G_bar;
			//				output_rec[n]->G_0_bar = G_0_bar;
			//				output_rec[n]->M_bar = M_bar;
			//				output_rec[n]->delta_Q_bar = delta_Q_bar;
			//				output_rec[n]->delta_Q_0_bar = delta_Q_0_bar;
			//				output_rec[n]->E_s_sum = E_s_sum;
			//				output_rec[n]->melt_sum = melt_sum;
			//				output_rec[n]->ro_pred_sum = ro_pred_sum;

		}
	}  /* for loop on grid */
	//	}







	return -1;

}
