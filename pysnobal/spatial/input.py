from pysnobal.core.constants import FREEZE
from pysnobal.point.libsnobal import sati
from pysnobal.point.input import InputData, InputDeltas


class InputSpatialData(InputData):

    def __init__(self, data, input_delta=False, init=0):

        self.net_solar = data['net_solar']
        self.incoming_thermal = data['incoming_thermal']
        self.air_temp = data['air_temp']
        self.vapor_pressure = data['vapor_pressure']
        self.wind_speed = data['wind_speed']
        self.soil_temp = data['soil_temp']
        self.precip_mass = data['precip_mass']
        self.percent_snow = data['percent_snow']
        self.rho_snow = data['rho_snow']
        self.precip_temp = data['precip_temp']

        # derived precip values
        self.m_snow = self.precip_mass * self.percent_snow
        self.m_rain = self.precip_mass - self.m_snow

        # initialize the other variables to 0
        for precip_derived in self.PRECIP_DERIVED:
            setattr(self, precip_derived, init)

        if not input_delta:
            self.precipitation_inputs()

    @property
    def t_a(self):
        return self._t_a

    @t_a.setter
    def t_a(self, var):
        self._t_a = var
        self.__sat_vp = False

    @property
    def sat_vp(self):
        """Calculate the saturation vapor pressure over ice for
        the air temperature

        Returns:
            float: saturation vapor pressure over ice
        """
        if not self.__sat_vp:
            self._sat_vp = sati(self.air_temp)
            self.__sat_vp = True
        return self._sat_vp

    @property
    def soil_temp(self):
        return self._soil_temp

    @soil_temp.setter
    def soil_temp(self, var):
        self._soil_temp = var
        self.__soil_vp = False

    @property
    def soil_vp(self):
        """Calculate the saturation vapor pressure over ice for
        the soil temperature

        Returns:
            float: saturation vapor pressure over ice
        """
        if not self.__soil_vp:
            self._soil_vp = sati(self.soil_temp)
            self.__soil_vp = True
        return self._soil_vp

    def precipitation_inputs(self):

        self.precip_now = False

        if self.precip_mass > 0:
            self.precip_now = True

            # self.precip_mass = self.precip_mass
            # self.m_snow = self.precip_mass * self.percent_snow
            # self.m_rain = self.precip_mass - self.m_snow

            if (self.m_snow > 0.0):
                if (self.rho_snow > 0.0):
                    self.z_snow = self.m_snow / self.rho_snow
                else:
                    raise ValueError(
                        'rho_snow is <= 0.0 with percent_snow > 0.0')
            else:
                self.z_snow = 0

            # check the precip, temp. cannot be below freezing if rain present
            if (self.m_rain > 0) and (self.precip_temp < FREEZE):
                self.precip_temp = FREEZE

            # Mixed snow and rain
            if (self.m_snow > 0) and (self.m_rain > 0):
                self.t_snow = FREEZE
                self.h2o_sat_snow = 1
                self.t_rain = self.precip_temp

            elif (self.m_snow > 0):
                # Snow only
                if (self.precip_temp < FREEZE):
                    # cold snow
                    self.t_snow = self.precip_temp
                    self.h2o_sat_snow = 0
                else:
                    # warm snow
                    self.t_snow = FREEZE
                    self.h2o_sat_snow = 1

            elif (self.m_rain > 0):
                # rain only
                self.t_rain = self.precip_temp

    def add_deltas(self, input_deltas):

        # Add the input data deltas
        self.net_solar = self.net_solar + input_deltas.net_solar
        self.incoming_thermal = self.incoming_thermal + \
            input_deltas.incoming_thermal
        self.air_temp = self.air_temp + input_deltas.air_temp
        self.vapor_pressure = self.vapor_pressure + input_deltas.vapor_pressure
        self.wind_speed = self.wind_speed + input_deltas.wind_speed
        self.soil_temp = self.soil_temp + input_deltas.soil_temp

        self.update_precip_deltas(input_deltas)

    def update_precip_deltas(self, input_deltas):

        # update the precipitation. Snobal takes the input deltas
        # and divides by the intervals
        for precip_variable in self.PRECIP_VARIABLES:
            setattr(self, precip_variable,
                    getattr(input_deltas, precip_variable))


class InputSpatialDeltas(InputDeltas):

    def __init__(self, input1, input2, tstep_info):

        super(InputSpatialData, self).__init__(
            input1, input2, tstep_info)

    def calculate(self):

        self.deltas = {}
        for tstep in self.tstep_info:

            tstep_deltas = {}
            for variable in self.input1.INPUT_VARIABLES:
                tstep_deltas[variable] = (
                    getattr(self.input2, variable) -
                    getattr(self.input1, variable)
                ) / tstep['intervals_per_timestep']

            for precip_variable in self.input1.PRECIP_VARIABLES:
                tstep_deltas[precip_variable] = \
                    getattr(self.input1, precip_variable) / \
                    tstep['intervals_per_timestep']

            for precip_constant in self.input1.PRECIP_CONSTANT:
                tstep_deltas[precip_constant] = \
                    getattr(self.input1, precip_constant)

            self.deltas[tstep['level']] = InputData(tstep_deltas)

        return self.deltas