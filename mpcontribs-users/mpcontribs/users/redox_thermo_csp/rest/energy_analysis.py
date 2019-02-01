# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import json
import os
import pandas as pd
from pymatgen.core.composition import Composition
from pymatgen.core.units import FloatWithUnit
from scipy.constants import R
from scipy.integrate import quad
from mpcontribs.users.redox_thermo_csp.rest.utils import remove_comp_one, add_comp_one, rootfind, s_th_o
from mpcontribs.users.redox_thermo_csp.rest.utils import dh_ds, funciso, funciso_theo, d_h_num_dev_calc
from mpcontribs.users.redox_thermo_csp.rest.utils import get_mpids_comps_perov_brownm, split_comp
from mpcontribs.users.redox_thermo_csp.rest.utils import redenth_act, find_active, get_debye_temp

class WaterSplitting:
    @staticmethod
    def dg_zero_water_splitting(temp):
        """
        Uses linear fits of data in Barin, Thermochemical Data of Pure Substances
        Only valid for steam!
        :return: dg_zero
        """
        dg_zero = ((-0.052489 * temp) + 245.039) * 1000
        return dg_zero

    @staticmethod
    def k_water_splitting(temp):
        """
        Get the equilibrium constant of water
        :param temp:    temperature in K
        :return: equilibrium constant
        """
        dg_zero = WaterSplitting().dg_zero_water_splitting(temp)
        k_eq = pd.np.exp(dg_zero / (-R * temp))
        return k_eq

    @staticmethod
    def get_h2_h2o_ratio(temp, po2):
        """
        Converts an oxygen partial pressure into a ratio of H2 to H2O for water splitting
        :param temp:    temperature in K
        :param po2:     oxygen partial pressure
        :return:        ratio of H2 to H2O
        """

        h2_h2o = WaterSplitting().k_water_splitting(temp) / pd.np.sqrt(po2)

        return h2_h2o

    @staticmethod
    def get_po2(temp, h2_h2o):
        """
        Converts a ratio of H2 to H2O for water splitting into an oxygen partial pressure
        :param temp:    temperature in K
        :param h2_h2o:  ratio of H2 to H2O
        :return:        oxygen partial pressure
        """

        po2 = (WaterSplitting().k_water_splitting(temp) / h2_h2o) ** 2

        return po2

class CO2Splitting:
    @staticmethod
    def dg_zero_co2_splitting(temp):
        """
        Uses linear fits of data in Barin, Thermochemical Data of Pure Substances
        :return: dg_zero
        """
        dg_zero_co2 = (temp ** 2) * 9.44E-7 - (0.0032113 * temp) - 393.523
        dg_zero_co = -0.0876385 * temp - 111.908

        dg_zero = (-dg_zero_co2 + dg_zero_co) * 1000

        return dg_zero

    @staticmethod
    def k_co2_splitting(temp):
        """
        Get the equilibrium constant of water
        :param temp:    temperature in K
        :return: equilibrium constant
        """

        dg_zero = CO2Splitting().dg_zero_co2_splitting(temp)
        k_eq = pd.np.exp(dg_zero / (-R * temp))

        return k_eq

    @staticmethod
    def get_co_co2_ratio(temp, po2):
        """
        Converts an oxygen partial pressure into a ratio of CO to CO2 for water spltting
        :param temp:    temperature in K
        :param po2:     oxygen partial pressure
        :return:        ratio of H2 to H2O
        """

        h2_h2o = CO2Splitting().k_co2_splitting(temp) / pd.np.sqrt(po2)

        return h2_h2o

    @staticmethod
    def get_po2(temp, co_co2):
        """
        Converts a ratio of CO to CO2 for water splitting into an oxygen partial pressure
        :param temp:    temperature in K
        :param h2_h2o:  ratio of H2 to H2O
        :return:        oxygen partial pressure
        """

        po2 = (CO2Splitting().k_co2_splitting(temp) / co_co2) ** 2

        return po2

class EnergyAnalysis:
    """
    Analyze the energy input for different redox cycles
    """

    def __init__(self, process="Air Separation"):
        self.process = process

    @staticmethod
    def c_p_water_liquid(temp):
        """
        Calculates the heat capacity of liquid water.
        :return: cp_water
        """
        # constants: Chase, NIST-JANAF Thermochemistry tables, Fourth Edition, 1998
        shomdat = [-203.6060, 1523.290, -3196.413, 2474.455, 3.855326]

        temp_frac = temp / 1000

        c_p_water = shomdat[0] + (shomdat[1] * temp_frac) + (shomdat[2] * (temp_frac ** 2)) + (
            shomdat[3] * (temp_frac ** 3)) + (shomdat[4] / (temp_frac ** 2))

        return c_p_water

    @staticmethod
    def c_p_steam(temp):
        """
        Calculates the heat capacity of steam
        :return: cp_steam
        """
        if temp < 1700:
            shomdat = [30.09200, 6.832514, 6.793435, -2.534480, 0.082139]
        else:
            shomdat = [41.96126, 8.622053, -1.499780, 0.098119, -11.15764]
        temp_frac = temp / 1000

        c_p_steam = shomdat[0] + (shomdat[1] * temp_frac) + (shomdat[2] * (temp_frac ** 2)) + (
        shomdat[3] * (temp_frac ** 3)) + (shomdat[4] / (temp_frac ** 2))

        return c_p_steam

    @staticmethod
    def get_heat_capacity(temp, td):
        # credits to Dr. Joseph Montoya, LBNL
        t_ratio = temp / td
        def integrand(x):
            return (x ** 4 * pd.np.exp(x)) / (pd.np.exp(x) - 1) ** 2
        if isinstance(t_ratio, int) or isinstance(t_ratio, float):
            cv_p = 9 * R * (t_ratio ** 3) * quad(integrand, 0, t_ratio ** -1)[0]
        else:
            cv_p = []
            for i in range(len(t_ratio)):
                cv_i = 9 * R * (t_ratio[i] ** 3) * quad(integrand, 0, t_ratio[i] ** -1)[0]
                cv_p = np.append(cv_p, cv_i)
        return cv_p * 5

    @staticmethod
    def get_heat_capacity_mixed(temp, delta, td_p=None, td_b=None):
        enal = EnergyAnalysis()
        cv_p = enal.get_heat_capacity(temp, td_p) * 5
        cv_b = enal.get_heat_capacity(temp, td_b) * 4.5
        ratio_p = (0.5 - delta) / 0.5
        ratio_b = delta / 0.5
        cv_m = pd.np.multiply(ratio_p, cv_p) + pd.np.multiply(ratio_b, cv_b)

        return temp, cv_m

    @staticmethod
    def heat_input_linear(temp_1, temp_2, delta_1, delta_2, t_d_perov, t_d_brownm, num=40):
        """
        Uses an approximation to calculate the integral c(T, delta)*T dT by splitting the interval into a number of
        slices with constant c
        Uses a linear approximation for delta between delta_1 and delta_2
        This method is a lot faster than the actual integration and the errors of the approximation are negligible
        (at default settings: < 1E-5, typically approx. 1E-6)
        :param temp_1:  initial temperature(s)
        :param temp_2:  final temperature(s)
        :param delta_1: initial non-stoichiometry value(s)
        :param delta_2: final non-stoichiometry values(s)
        :param num:     number of steps for the approximation of the integral
        :return:        heat input to heat perovskite from temp_1 to temp_2 considering the change in delta (in J)
                        positive for heating, negative for cooling
        """

        try:
            # treatment of arrays for output of multiple data points
            dqs = []
            if not (isinstance(temp_1, float) or (isinstance(temp_1, int))):
                for i in range(len(temp_1)):
                    tempval = pd.np.linspace(temp_1[i], temp_2[i], num=num)
                    deltaval = pd.np.linspace(delta_1[i], delta_2[i], num=num)

                    # calculate average values within intervals
                    delta_x0_x1 = pd.np.empty(len(deltaval) - 1)
                    for i in range(len(deltaval) - 1):
                        delta_x0_x1[i] = (deltaval[i] + deltaval[i + 1]) / 2

                    temp_x0_x1 = pd.np.empty(len(tempval) - 1)
                    for i in range(len(tempval) - 1):
                        temp_x0_x1[i] = (tempval[i] + tempval[i + 1]) / 2

                    # length of a temperature step
                    del_temp = (temp_2 - temp_1) / len(temp_x0_x1)

                    # calculate the area under the step for each step
                    dq = 0
                    for i in range(len(delta_x0_x1)):
                        cv_step = EnergyAnalysis().get_heat_capacity_mixed(temp_x0_x1[i], delta_x0_x1[i], td_p=t_d_perov,
                        td_b=t_d_brownm)[1]
                        q_step = cv_step * del_temp
                        dq += q_step
                    dqs = pd.np.append(dqs, dq)
                dq = dqs

            else:
                tempval = pd.np.linspace(temp_1, temp_2, num=num)
                deltaval = pd.np.linspace(delta_1, delta_2, num=num)

                # calculate average values within intervals
                delta_x0_x1 = pd.np.empty(len(deltaval) - 1)
                for i in range(len(deltaval) - 1):
                    delta_x0_x1[i] = (deltaval[i] + deltaval[i + 1]) / 2

                temp_x0_x1 = pd.np.empty(len(tempval) - 1)
                for i in range(len(tempval) - 1):
                    temp_x0_x1[i] = (tempval[i] + tempval[i + 1]) / 2

                # length of a temperature step
                del_temp = (temp_2 - temp_1) / len(temp_x0_x1)

                # calculate the area under the step for each step
                dq = 0
                for i in range(len(delta_x0_x1)):
                    cv_step = EnergyAnalysis().get_heat_capacity_mixed(temp_x0_x1[i], delta_x0_x1[i], td_p=t_d_perov,
                    td_b=t_d_brownm)[1]
                    q_step = cv_step * del_temp
                    dq += q_step

        except TypeError:
            dq = None
            raise ValueError("Elastic tensors or crystal structures not available for this set of materials.")

        return dq

    @staticmethod
    def energy_steam_generation(temp_1, temp_2, h_2_h2o, celsius=True, h_rec=0.0):
        """
        Calculates the energy required to heat water, evaporate it and to generate steam at temperature "temp"
        Assuming water at ambient pressure, boiling point 100 °C
        :param temp_1:  initial temperature of water/steam
        :param temp_2:  steam temperature
        :param h_2_h2o: partial pressure ratio h2/h2o
        :param celsius: if True, temperature values are assumed to be in degrees celsius
        :param h_rec:   heat recovery efficiency, can be between 0 and 1
        :return:        energy required to generate steam per mol of H2 in the product stream in kJ/mol
        """

        if celsius:
            temp_1 = temp_1 + 273.15
            temp_2 = temp_2 + 273.15
        enal = EnergyAnalysis()

        # liquid water (at ambient pressure)
        # this code only considers water at ambient pressure!
        if temp_1 < 373.15:
            if temp_2 > 373.15:
                energy_1 = quad(enal.c_p_water_liquid, temp_1, 373.15)[0]
            else:
                energy_1 = quad(enal.c_p_water_liquid, temp_1, temp_2)[0]
        else:
            energy_1 = 0

        if temp_2 > 373.15:
            if temp_1 < 373.15:
                energy_2 = quad(enal.c_p_steam, 373.15, temp_2)[0]
            else:
                energy_2 = quad(enal.c_p_steam, temp_1, temp_2)[0]
        else:
            energy_2 = 0

        # from the literature
        heat_vaporization = 40790

        if temp_1 < 373.15 < temp_2:
            total_energy = energy_1 + energy_2 + heat_vaporization
        else:
            total_energy = energy_1 + energy_2

        # per mol of H2
        total_energy = total_energy / h_2_h2o
        # considering heat recovery
        total_energy = total_energy * (1 - h_rec)

        return total_energy / 1000

    @staticmethod
    def energy_integral_theo(enth_steps, celsius, temp_1, temp_2, compstr, dh_min, dh_max, t_d_perov, t_d_brownm,
                             p_o_2_1, p_o_2_2):
        """
        Determines the chemical energy change using theoretical data. All variables explained in
        EnergyAnalysis.calc
        """

        # To get a good approximation of the integral over the enthalpy values, the area under the curve is calculated
        # stepwise. The actual integral calculation would take too long, as each enthalpy value is calculated
        # numerically

        # We are only considering the case of linear change of both pressure and temperature between reduction and oxidation here
        if celsius:
            tempval = pd.np.linspace(temp_1 + 273.15, temp_2 + 273.15, num=enth_steps)
        else:
            tempval = pd.np.linspace(temp_1, temp_2, num=enth_steps)

        p_val = pd.np.logspace(pd.np.log10(p_o_2_1), pd.np.log10(p_o_2_2), num=enth_steps)
        sample_spl = split_comp(compstr)
        act = find_active(mat_comp=sample_spl)[1]

        delta_vals = []
        for i in range(len(tempval)):
            args_theo = (pd.np.log(p_val[i]), tempval[i], None, t_d_perov, t_d_brownm, dh_min, dh_max, act)
            delta_val_i = rootfind(1e-10, 0.5-1e-10, args_theo, funciso_theo)
            delta_vals = pd.np.append(delta_vals, delta_val_i)

        dh_vals = []
        for i in range(len(tempval)):
            dh_i = d_h_num_dev_calc(delta=delta_vals[i], dh_1=dh_min, dh_2=dh_max, temp=tempval[i], act=act)
            dh_vals = pd.np.append(dh_vals, dh_i)

        # calculate energy stepwise
        energy_red = []
        for i in range(len(delta_vals) - 1):
            # deltastep * average dh
            h_x0_x1_i = (dh_vals[i] + dh_vals[i + 1]) / 2
            energy_i = (delta_vals[i + 1] - delta_vals[i]) * h_x0_x1_i
            energy_red = pd.np.append(energy_red, energy_i)

        energy_integral_dh = sum(energy_red) / 1000

        return energy_integral_dh

    @staticmethod
    def mechanical_envelope(p_red):
        """
        Uses the "mechanical envelope" function from Stefan Brendelberger et al.
        dx.doi.org/10.1016/j.solener.2016.11.023
        Estimates the energy required to pump one mol of oxygen at this pressure using mechanical pumps.

        :param p_red:                   oxygen partial pressure at reduction conditions

        :return: pump_ener_envelope:    mechanical energy required to pump one mol of O
        """

        if (p_red < 1E-6) or (p_red > 0.7):
            q_pump = float('inf') # mechanical envelope not applicable in this range
        else:
            eff_sol = 0.4

            temp = 473  # this is the operating temperature of the pump
            a0 = 0.30557
            a1 = -0.17808
            a2 = -0.15514
            a3 = -0.03173
            a4 = -0.00203
            p0 = 1e5
            p = p_red * p0

            eff = a0 + a1*pd.np.log10(p/p0) + a2*(pd.np.log10(p/p0))**2 + a3*(pd.np.log10(p/p0))**3 + a4*(pd.np.log10(p/p0))**4
            q_iso=R*temp*pd.np.log(p0/p)
            q_pump=(q_iso/eff) / eff_sol
            q_pump = q_pump / 2000

        return q_pump

    @staticmethod
    def dhf_h2o(t_ox):
        """
        Gets the heat of formation of water for at certain temperature
        Based on the Shomate equation and the NIST-JANAF thermochemical tables
        H° − H°298.15= A*t + B*t2/2 + C*t3/3 + D*t4/4 − E/t + F − H
        H° = A*t + B*t2/2 + C*t3/3 + D*t4/4 − E/t + F
        https://webbook.nist.gov/cgi/cbook.cgi?ID=C7732185&Units=SI&Mask=1#Thermo-Gas
        """

        if t_ox <= 1700:
            a = 30.09200
            b = 6.832514
            c = 6.793435
            d = -2.534480
            e = 0.082139
            f = -250.8810

        else:
            a = 41.96426
            b = 8.622053
            c = -1.499780
            d = 0.098119
            e = -11.15764
            f = -272.1797

        t_1000 = t_ox / 1000
        hform = a*t_1000
        hform += 0.5*b*(t_1000**2)
        hform += (1/3)*c*(t_1000**3)
        hform += (1/4)*c*(t_1000**4)
        hform += -e/t_1000
        hform += f

        return hform

    @staticmethod
    def dh_co_co2(t_ox):
        """
        Gets the heat of formation of CO2 and of CO and returns the difference to get the heat of reaction
        Based on the Shomate equation and the NIST-JANAF thermochemical tables
        H° − H°298.15= A*t + B*t2/2 + C*t3/3 + D*t4/4 − E/t + F − H
        H° = A*t + B*t2/2 + C*t3/3 + D*t4/4 − E/t + F

        CO2: https://webbook.nist.gov/cgi/cbook.cgi?ID=C124389&Units=SI&Mask=1#Thermo-Gas
        CO:  https://webbook.nist.gov/cgi/cbook.cgi?ID=C630080&Units=SI&Mask=1#Thermo-Gas
        """
        t_1000 = t_ox / 1000

        # CO2
        if t_ox <= 1200:
            a = 24.99735
            b = 55.18696
            c = -33.69137
            d = 7.948387
            e = -0.136638
            f = -403.6075

        else:
            a = 58.16639
            b = 2.720074
            c = -0.492289
            d = 0.038844
            e = -6.447293
            f = -425.9186

        hco2 = a*t_1000
        hco2 += 0.5*b*(t_1000**2)
        hco2 += (1/3)*c*(t_1000**3)
        hco2 += (1/4)*c*(t_1000**4)
        hco2 += -e/t_1000
        hco2 += f

        # CO
        if t_ox <= 1300:
            a = 25.56759
            b = 6.096130
            c = 4.054656
            d = -2.671301
            e = 0.131021
            f = -118.0089

        else:
            a = 35.15070
            b = 1.300095
            c = -0.205921
            d = 0.013550
            e = -3.282780
            f = -127.8375

        hco = a*t_1000
        hco += 0.5*b*(t_1000**2)
        hco += (1/3)*c*(t_1000**3)
        hco += (1/4)*c*(t_1000**4)
        hco += -e/t_1000
        hco += f

        return hco2-hco

    def calc(self, p_ox, p_red, t_ox, t_red, data_origin="Exp", data_use="combined",
             enth_steps=30, sample_ident=-1, celsius=True, from_file=True,
             heat_cap=True,
             heat_cap_approx=True
             ):

        """
        Performs an energy analysis using experimental data.

        :param p_ox:    Oxidation partial pressure of oxygen (in bar) or ratio p(H2)/p(H2O) / p(CO)/p(CO2)
        :param p_red:   Oxygen partial pressure for reduction (in bar)
        :param t_ox:    Oxidation temperature
        :param t_red:   Reduction temperature

        :param data_origin:     "Exp":  experimental data
                                "Theo": theoretical data

            ***only relevant if 'data_origin' = "Theo"
            :param data_use:
                                "endmembers": uses redox members of solid solution endmembers to estimate redox
                                              enthalpies of solid solutions
                                "combined":   corrects above-mentioned data by the actual redox enthalpies for the solid
                                              solutions calcualted via DFT

            :param enth_steps:      number of enthalpy values which are calculated for each material in order to
                                    reach a good approximation of the integral over dH vs. delta

        :param sample_ident:   Sample number(s) (experimental data) or composition (theoretical data),
                               default value '-1'-> analyze all samples

        :param pump_ener:   allows to consider the pumping energy required to pump from p_o_2_1 to p_o_2_2
                            input in kJ per kg of redox material in the oxidized state + the losses
                            This depends on many factors, such as the type of pumps used, the volume of the
                            reaction chamber, the reactor type etc., so the user needs to calculate this
                            value beforehand depending on the individual process conditions
                            In case some of the pumping energy can be recovered, this share needs to be
                            subtracted beforehand, as it is not considered herein.

        :param celsius:             if True, assumes all input temperatures are in °C instead of K

        :param from_file:           if True, takes the enthalpies, Debye temperatures, and materials lists from
                                    the file "theo_redenth_debye.json". Much faster than using the MPRester
                                    Only works if sample_ident = -1

        :param heat_cap:            if True, sensible energy to heat the samples is considered
        :param heat_cap_approx:     if True, uses values for SrFeOx in case of missing heat capacity data

        :return:    dict_result: dictonary with results for different materials
        """
        si_first = sample_ident
        # correct temperature values for Kelvin/Celsius
        if celsius:
            temp_1_corr = t_ox + 273.15
            temp_2_corr = t_red + 273.15
        else:
            temp_1_corr = t_ox
            temp_2_corr = t_red

        if data_origin == "Exp": # currently not in use for updates of existing data
            # load experimental sample data from file
            path = os.path.abspath("")
            filepath = os.path.join(path, "exp_data.json")
            with open(filepath) as handle:
                expdata = json.loads(handle.read())

        # use equivalent partial pressures for Water Splitting and CO2 splitting
        if self.process == "Water Splitting":
            p_ox = WaterSplitting().get_po2(temp=temp_1_corr, h2_h2o=p_ox)
        elif self.process == "CO2 Splitting":
            p_ox = CO2Splitting().get_po2(temp=temp_1_corr, co_co2=p_ox)

        # iterate over samples
        if isinstance(sample_ident, collections.Sized) and not isinstance(sample_ident, str):
            no_range = range(len(sample_ident))
            sample = None
        else:
            no_range = range(1)
            if data_origin == "Exp":
                sample = int(sample_ident)
            else:
                sample = str(sample_ident)
            # iterate over all available samples
            if sample_ident == -1:
                sample = None
                if data_origin == "Exp":
                    no_range = range(0, 150)
                    sample_ident = no_range
                else:
                    if not from_file:
                        filename = os.path.join(os.path.abspath('..'), "datafiles", "perovskite_theo_list.csv")
                        if not os.path.exists(filename):
                            raise ImportError("File 'perovskite_theo_list.csv' not found.")
                        fo = open(filename, "rb")
                        sample_ident = pd.np.genfromtxt(fo, dtype='str', delimiter=",", skip_header=1)
                        fo.close()
                    else:
                        sampledata = views.get_theo_data()
                        sample_ident = sampledata["compstr"]
                    no_range = range(len(sample_ident))

        sample_l, chemical_energy_l, sensible_energy_l, mol_mass_ox_l, prodstr_alt_l = [], [], [], [], []
        mol_prod_mol_red_l, t_ox_l, t_red_l, p_ox_l, p_red_l, compstr_l = [], [], [], [], [], []
        delta_1_l, delta_2_l, mass_redox_l, prodstr_l, l_prod_kg_red_l, g_prod_kg_red_l = [], [], [], [], [], []
        for i in no_range:
            if not sample:
                sample = sample_ident[i]
            # this only works if the sample number/data exists
            try:
                if data_origin == "Exp":
                    exp_index = -1
                    for k in range(len(expdata)):
                        if int(expdata["Sample number"][k]) == sample:
                            exp_index = k
                    if exp_index == -1:
                        raise ValueError("Experimental data for this sample not found.")
                    compstr = expdata["theo_compstr"][exp_index]
                    compstr_x = compstr.split("Ox")[0]

                    # this formats the parameters the same way we have them in views.py
                    fit_param_enth = {"a": float(expdata["dH_max"][exp_index]),
                                      "b": float(expdata["dH_min"][exp_index]),
                                      "c": float(expdata["t"][exp_index]),
                                      "d": float(expdata["s"][exp_index])}
                    fit_type_entr = str(expdata["fit type entropy"][exp_index])
                    if fit_type_entr == "Dilute_Species":
                        fit_par_ent = {"a": float(expdata["entr_dil_s_v"][exp_index]),
                                          "b": float(expdata["entr_dil_a"][exp_index]),
                                          "c": float(expdata["delta_0"][exp_index])}
                    else:
                        fit_par_ent = {"a": float(expdata["entr_solid_sol_s"][exp_index]),
                                          "b": float(expdata["entr_solid_sol_shift"][exp_index]),
                                          "c": float(expdata["delta_0"][exp_index])}
                    theo_compstr = compstr
                    splitcomp = split_comp(compstr)
                    delta_0 = float(expdata["delta_0"][exp_index])
                    actf = find_active(mat_comp=splitcomp)[1]
                    act_mat = {"Material": float(actf)}
                    fit_param_fe = {"a": 231.062,
                                      "b": -24.3338,
                                      "c": 0.839785,
                                      "d": 0.219157}
                    pars = { "fit_par_ent": fit_par_ent,
                            "fit_param_enth": fit_param_enth,
                            "fit_type_entr": fit_type_entr,
                            "delta_0": delta_0,
                            "fit_param_fe": fit_param_fe,
                            "act_mat": act_mat
                            }

                    args_1 = (pd.np.log(p_ox), temp_1_corr, pars, s_th_o(temp_1_corr))
                    args_2 = (pd.np.log(p_red), temp_2_corr, pars, s_th_o(temp_2_corr))
                    delta_1 = rootfind(1e-10, 0.5-1e-10, args_1, funciso)
                    delta_2 = rootfind(1e-10, 0.5-1e-10, args_2, funciso)

                    # use theoretical elastic tensors
                    sampledata = views.get_theo_data()
                    for z in range(len(sampledata["compstr"])):
                        if (sampledata["compstr"][z]).split("O3")[0] == compstr.split("Ox")[0]:
                            index_debye = z
                    t_d_perov = float(sampledata["Debye temp perovskite"][index_debye])
                    t_d_brownm = float(sampledata["Debye temp brownmillerite"][index_debye])
                else:
                    # if composition does not contain ones as stoichiometries, add them
                    sample = add_comp_one(compstr=sample)
                    if not from_file or si_first != -1:
                        try:
                            red_active = redenth_act(sample)
                        except TypeError:
                            raise ValueError("Enthalpy data not available for this material.")
                        h_min = red_active[1]
                        h_max = red_active[2]
                        act = red_active[3]
                    else:
                        h_min = float(sampledata["dH_min"][i])
                        h_max = float(sampledata["dH_max"][i])
                        act = float(sampledata["act"][i])
                    compstr = sample
                    compstr_x = compstr.split("O")[0]

                    if not from_file or si_first != -1:
                        try: # get Debye temperatures for vibrational entropy
                            mp_ids = get_mpids_comps_perov_brownm(compstr=compstr)
                            t_d_perov = get_debye_temp(mp_ids[0])
                            t_d_brownm = get_debye_temp(mp_ids[1])
                        except Exception as e: # if no elastic tensors or no data for this material is available
                            mp_ids = ("mp-510624", "mp-561589") # using data for SrFeOx if no data is available (close approximation)
                            t_d_perov = get_debye_temp(mp_ids[0])
                            t_d_brownm = get_debye_temp(mp_ids[1])
                    else:
                        t_d_perov = float(sampledata["Debye temp perovskite"][i])
                        t_d_brownm = float(sampledata["Debye temp brownmillerite"][i])

                    args_theo_1 = (pd.np.log(p_ox), temp_1_corr, None, t_d_perov, t_d_brownm, h_min, h_max, act)
                    delta_1 = rootfind(1e-10, 0.5-1e-10, args_theo_1, funciso_theo)
                    args_theo_2 = (pd.np.log(p_red), temp_2_corr, None, t_d_perov, t_d_brownm, h_min, h_max, act)
                    delta_2 = rootfind(1e-10, 0.5-1e-10, args_theo_2, funciso_theo)

                # calculate the mass change in %
                comp_ox = compstr_x + "O" + str(float(3 - delta_1))
                comp_red = compstr_x + "O" + str(float(3 - delta_2))
                mol_mass_ox = float(Composition(comp_ox).weight)
                mol_mass_red = float(Composition(comp_red).weight)
                mass_redox_i = ((mol_mass_ox - mol_mass_red) / mol_mass_ox) * 100

                # define reaction products
                if self.process == "Air Separation":
                    prodstr = "O2"
                    prodstr_alt = "O"
                elif self.process == "Water Splitting":
                    prodstr = "H2"
                    prodstr_alt = prodstr
                elif self.process == "CO2 Splitting":
                    prodstr = "CO"
                    prodstr_alt = prodstr
                else:
                    raise ValueError("Process must be either Air Separation, Water Splitting, or CO2 Splitting!")

                # only continue if the user-designated reduction step actually leads to reduction
                # if not, set result to infinite
                if delta_2 < delta_1:
                    ener_i = pd.np.ones(5) * float('inf')
                    per_kg_redox = pd.np.ones(5) * float('inf')
                    per_kg_wh_redox = pd.np.ones(5) * float('inf')
                    kj_mol_prod = pd.np.ones(5) * float('inf')
                    energy_l = pd.np.ones(5) * float('inf')
                    energy_l_wh = pd.np.ones(5) * float('inf')
                    efficiency = float('inf')
                    mol_prod_mol_red = float('inf')
                    l_prod_kg_red = float('inf')
                    g_prod_kg_red = float('inf')

                else:
                    # mol product per mol of redox material
                    mol_prod_mol_red = delta_2 - delta_1
                    # L product per kg of redox material (SATP)
                    l_prod_kg_red = mol_prod_mol_red * (24.465 / (0.001 * mol_mass_ox))
                    # convert mol O to mol O2
                    if self.process == "Air Separation":
                        l_prod_kg_red = l_prod_kg_red * 0.5
                    # g product per kg redox material
                    g_prod_kg_red = float(Composition(prodstr).weight) * (l_prod_kg_red / 24.465)

                    if data_origin == "Exp":
                        d_delta = delta_0
                    else:
                        d_delta = 0.0
                    # correct for d_delta
                    d_delta_1 = delta_1 - d_delta
                    d_delta_2 = delta_2 - d_delta

                    # chemical energy
                    if data_origin == "Exp":
                        s_th_mean = (s_th_o(temp_1_corr) + s_th_o(temp_1_corr)) / 2
                        def dh_func_exp(d_delta_func):
                            return dh_ds(d_delta_func, s_th_mean, pars)[0]
                        energy_integral_dh = quad(dh_func_exp, d_delta_1, d_delta_2)[0]
                        if energy_integral_dh < 0:
                            raise ValueError("negative chemical energy due to insuffiencent experimental data...skipping this sample")
                    else:
                        energy_integral_dh = EnergyAnalysis(process=self.process).energy_integral_theo(
                             celsius=celsius, compstr=compstr, dh_max=h_max,
                            dh_min=h_min, enth_steps=enth_steps, p_o_2_1=p_ox, p_o_2_2=p_red, temp_1=t_ox, temp_2=t_red,
                            t_d_perov=t_d_perov, t_d_brownm = t_d_brownm)

                    # sensible energy
                    energy_sensible = 0
                    if heat_cap:
                        energy_sensible = EnergyAnalysis().heat_input_linear(temp_1=temp_1_corr, temp_2=temp_2_corr, delta_1=delta_1,
                            delta_2=delta_2, t_d_perov=t_d_perov, t_d_brownm=t_d_brownm, num=40) / 1000

                chemical_energy_l.append(energy_integral_dh)
                sensible_energy_l.append(energy_sensible)
                mol_mass_ox_l.append(mol_mass_ox)
                mol_prod_mol_red_l.append(mol_prod_mol_red)
                t_ox_l.append(temp_1_corr)
                t_red_l.append(temp_2_corr)
                p_ox_l.append(p_ox)
                p_red_l.append(p_red)
                compstr_l.append(compstr)
                delta_1_l.append(delta_1)
                delta_2_l.append(delta_2)
                mass_redox_l.append(mass_redox_i)
                prodstr_l.append(prodstr)
                prodstr_alt_l.append(prodstr_alt)
                l_prod_kg_red_l.append(l_prod_kg_red)
                g_prod_kg_red_l.append(g_prod_kg_red)

            # skip this sample if the sample number does not exist
            except Exception as e:
                pass
                #print("No data for sample " + str(sample) + " found!" + str(e))
            sample = None

        resdict = { "Chemical Energy": chemical_energy_l,
                    "Sensible Energy": sensible_energy_l,
                    "mol_mass_ox": mol_mass_ox_l,
                    "mol_prod_mol_red": mol_prod_mol_red_l,
                    "T_ox": t_ox_l,
                    "T_red": t_red_l,
                    "p_ox": p_ox_l,
                    "p_red": p_red_l,
                    "compstr": compstr_l,
                    "delta_1": delta_1_l,
                    "delta_2": delta_2_l,
                    "mass_redox": mass_redox_l,
                    "prodstr": prodstr_l,
                    "prodstr_alt": prodstr_alt_l,
                    "l_prod_kg_red": l_prod_kg_red_l,
                    "g_prod_kg_red": g_prod_kg_red_l}
        return resdict

    def on_the_fly(self, resdict, pump_ener, w_feed, h_rec, h_rec_steam, celsius=True, h_val="high", p_ox_wscs=0, rem_unstable=True):
        """
        Allows to calculate the energy input for different conditions rather quickly, without having to re-calculate
        the time-intensive chemical and sensible energy every time again

        :param resdict:     dictionary with results (mainly for chemical and sesible energy, as calculated by
                            EnergyAnalysis().calc()

        :param pump_ener:   allows to consider the pumping energy required to pump from p_o_2_1 to p_o_2_2
                            input in kJ per kg of redox material in the oxidized state + the losses
                            This depends on many factors, such as the type of pumps used, the volume of the
                            reaction chamber, the reactor type etc., so the user needs to calculate this
                            value beforehand depending on the individual process conditions
                            In case some of the pumping energy can be recovered, this share needs to be
                            subtracted beforehand, as it is not considered herein.

        :param h_rec:               heat recovery efficiency factor (0...1) for chemical and sensible energy

        ***these values are only relevant for water splitting***
        :param h_rec_steam:         heat recovery efficiency factor (0...1) for recovery of heat stored in the steam
        :param w_feed:              water inlet temperature (in °C or K as defined by 'celsius')
        :param h_val:               heating value of hydrogen: 'low' -> lower heating value,
                                                               'high' -> higher heating value

        :param p_ox_wscs:   ratio H2/H2O / ratio CO/CO2

        :param rem_unstable: if True, phases which are potentially unstable for chemical reasons are removed
                            this is based on the phases in "unstable_phases.json"
                            currently, phases are excluded for the following reasons:
                            - tolerance factor below 0.9 (e.g. EuCuO3, which cannot be synthesized as opposed to EuFeO3)
                            - phases with expected high covalency (V5+ cations, for instance, NaVO3 is stable but not a perovskite)
                            - phases with expected low melting point (Mo5+ cations, see this article for NaMoO3
                            http://www.journal.csj.jp/doi/pdf/10.1246/bcsj.64.161)

                            By default, this is always True and there is no way in the user front-end to change this.
                            However, this could be changed manually by the developers, if neccessary.
        """
        if self.process == "Air Separation":
            p_ox_wscs = 1

        # initialize result variables
        result_val_ener_i = pd.np.empty(6)
        result_val_per_kg_redox = pd.np.empty(6)
        result_val_per_kg_wh_redox = pd.np.empty(6)
        result_val_per_kj_mol_prod = pd.np.empty(6)
        result_val_per_energy_l = pd.np.empty(6)
        result_val_per_energy_l_wh = pd.np.empty(6)
        result_val_efficiency = pd.np.empty(2)
        result_val_mol_prod_mol_red = pd.np.empty(2)
        result_val_l_prod_kg_red = pd.np.empty(2)
        result_val_g_prod_kg_red = pd.np.empty(2)
        result_val_delta_redox = pd.np.empty(2)
        result_val_mass_change = pd.np.empty(2)

        for rd in resdict:
            chemical_energy = rd['Chemical Energy']
            energy_sensible = rd['Sensible Energy']
            t_ox = rd['T_ox']
            t_red = rd['T_red']
            t_mean = (t_ox + t_red) / 2
            delta_1 = rd['delta_1']
            delta_2 = rd['delta_2']
            g_prod_kg_red = rd['g_prod_kg_red']
            l_prod_kg_red = rd['l_prod_kg_red']
            mass_redox_i = rd['mass_redox']
            mol_mass_ox = rd['mol_mass_ox']
            mol_prod_mol_red = rd['mol_prod_mol_red']
            p_ox = rd['p_ox']
            p_red = rd['p_red']
            compstr = rd['compstr']
            prodstr = rd['prodstr']
            prodstr_alt = rd['prodstr_alt']
            unstable = rd['unstable']

            # chemical energy stored in products
            if self.process == "Water Splitting":
                dh_wscs = EnergyAnalysis().dhf_h2o(t_mean) * mol_prod_mol_red
            elif self.process == "CO2 Splitting":
                dh_wscs = EnergyAnalysis().dh_co_co2(t_mean) * mol_prod_mol_red
            else:
                dh_wscs = 0

            energy_integral_dh = chemical_energy - ( (chemical_energy + dh_wscs) * h_rec )

            if len(resdict) < 50: # for experimental data: convert J/mol to kJ/mol
                energy_integral_dh = energy_integral_dh / 1000
                # wscs does not matter, as no water splitting / co2 splitting is considered for exp data

            # pumping energy
            if pump_ener != -1:
                energy_pumping = (float(pump_ener) * mol_mass_ox) / 1000
            else:  # using mechanical envelope
                # per mol O
                energy_pumping = EnergyAnalysis().mechanical_envelope(p_red=p_red)
                # per mol material
                energy_pumping = energy_pumping * mol_prod_mol_red

            # steam generation
            if self.process == "Water Splitting" and h_rec_steam != 1:
                energy_steam = mol_prod_mol_red * EnergyAnalysis().energy_steam_generation(temp_1=w_feed,
                temp_2=((t_ox+t_red)*0.5)-273.15,
                h_2_h2o=p_ox_wscs,
                celsius=celsius,
                h_rec=h_rec_steam)
            else:
                energy_steam = 0

            # total energy
            energy_total = energy_integral_dh  + energy_sensible * (1 - h_rec) + energy_pumping + energy_steam

            ener_i = pd.np.array([energy_total, energy_integral_dh, energy_sensible * (1 - h_rec),
            energy_pumping,
            energy_steam])

            # kJ/kg of redox material
            per_kg_redox = (ener_i / mol_mass_ox) * 1000
            # Wh/kg of redox material
            per_kg_wh_redox = per_kg_redox / 3.6
            # kJ/mol of product (O, H2, or CO)
            kj_mol_prod = ener_i / (delta_2 - delta_1)
            # kJ/L of product (ideal gas at SATP)
            energy_l = kj_mol_prod / 24.465
            # convert from O to O2
            if self.process == "Air Separation":
                energy_l = 2 * energy_l
            # Wh/L of product (ideal gas at SATP)
            energy_l_wh = energy_l / 3.6

            # calculate efficiency for water splitting
            if self.process == "Water Splitting":
                # source for heating values
                # https://h2tools.org/node/3131
                if h_val == "low":
                    h_v = 119.96
                elif h_val == "high":
                    h_v = 141.88
                else:
                    raise ValueError("heating_value must be either 'high' or 'low'")
                # convert kJ/mol H2 to MJ/kg H2 -> divide by 2.016
                efficiency = (h_v / (kj_mol_prod[0] / 2.016)) * 100
            else:
                efficiency = None

            delta_redox_i = [float(delta_2 - delta_1)]
            mass_change_i = [float(mass_redox_i)]
            compdisp = remove_comp_one(compstr=compstr)

            invalid_val = False # remove data of unstable compounds
            if rem_unstable and unstable:
                invalid_val = True

            # append new values to result and add compositions
            if (ener_i[0] < 0) or invalid_val: # sort out negative values, heat input is always positive
                ener_i[0] = float('inf')
            res_i = pd.np.append(ener_i, compdisp)
            result_val_ener_i = pd.np.vstack((result_val_ener_i, res_i))

            if per_kg_redox[0] < 0 or invalid_val:
                per_kg_redox[0] = float('inf')
            res_i = pd.np.append(per_kg_redox, compdisp)
            result_val_per_kg_redox = pd.np.vstack((result_val_per_kg_redox, res_i))

            if per_kg_wh_redox[0] < 0 or invalid_val:
                per_kg_wh_redox[0] = float('inf')
            res_i = pd.np.append(per_kg_wh_redox, compdisp)
            result_val_per_kg_wh_redox = pd.np.vstack((result_val_per_kg_wh_redox, res_i))

            if kj_mol_prod[0] < 0 or invalid_val:
                kj_mol_prod[0] = float('inf')
            res_i = pd.np.append(kj_mol_prod, compdisp)
            result_val_per_kj_mol_prod = pd.np.vstack((result_val_per_kj_mol_prod, res_i))

            if energy_l[0] < 0 or invalid_val:
                energy_l[0] = float('inf')
            res_i = pd.np.append(energy_l, compdisp)
            result_val_per_energy_l = pd.np.vstack((result_val_per_energy_l, res_i))

            if energy_l_wh[0] < 0 or invalid_val:
                energy_l_wh[0] = float('inf')
            res_i = pd.np.append(energy_l_wh, compdisp)
            result_val_per_energy_l_wh = pd.np.vstack((result_val_per_energy_l_wh, res_i))

            if efficiency < 0 or invalid_val:
                efficiency = float('-inf')
            res_i = pd.np.append(efficiency, compdisp)
            result_val_efficiency = pd.np.vstack((result_val_efficiency, res_i))

            if mol_prod_mol_red < 0 or invalid_val:
                mol_prod_mol_red = float('-inf')
            res_i = pd.np.append(mol_prod_mol_red, compdisp)
            result_val_mol_prod_mol_red = pd.np.vstack((result_val_mol_prod_mol_red, res_i))

            if l_prod_kg_red < 0 or invalid_val:
                l_prod_kg_red = float('-inf')
            res_i = pd.np.append(l_prod_kg_red, compdisp)
            result_val_l_prod_kg_red = pd.np.vstack((result_val_l_prod_kg_red, res_i))

            if g_prod_kg_red < 0 or invalid_val:
                g_prod_kg_red = float('-inf')
            res_i = pd.np.append(g_prod_kg_red, compdisp)
            result_val_g_prod_kg_red = pd.np.vstack((result_val_g_prod_kg_red, res_i))

            if delta_redox_i < 0 or invalid_val:
                delta_redox_i = float('-inf')
            res_i = pd.np.append(delta_redox_i, compdisp)
            result_val_delta_redox = pd.np.vstack((result_val_delta_redox, res_i))

            if mass_change_i < 0 or invalid_val:
                mass_change_i = float('-inf')
            res_i = pd.np.append(mass_change_i, compdisp)
            result_val_mass_change = pd.np.vstack((result_val_mass_change, res_i))

        # sort results
        result_val_ener_i = sorted(result_val_ener_i[1:], key=lambda x: float(x[0]))
        result_val_per_kg_redox = sorted(result_val_per_kg_redox[1:], key=lambda x: float(x[0]))
        result_val_per_kg_wh_redox = sorted(result_val_per_kg_wh_redox[1:], key=lambda x: float(x[0]))
        result_val_per_kj_mol_prod = sorted(result_val_per_kj_mol_prod[1:], key=lambda x: float(x[0]))
        result_val_per_energy_l = sorted(result_val_per_energy_l[1:], key=lambda x: float(x[0]))
        result_val_per_energy_l_wh = sorted(result_val_per_energy_l_wh[1:], key=lambda x: float(x[0]))
        if self.process == "Water Splitting":
            result_val_efficiency = sorted(result_val_efficiency[1:], key=lambda x: float(x[0]), reverse=True)
        else:
            result_val_efficiency = result_val_efficiency[1:]
        result_val_mol_prod_mol_red = sorted(result_val_mol_prod_mol_red[1:], key=lambda x: float(x[0]), reverse=True)
        result_val_l_prod_kg_red = sorted(result_val_l_prod_kg_red[1:], key=lambda x: float(x[0]), reverse=True)
        result_val_g_prod_kg_red = sorted(result_val_g_prod_kg_red[1:], key=lambda x: float(x[0]), reverse=True)
        result_val_delta_redox = sorted(result_val_delta_redox[1:], key=lambda x: float(x[0]), reverse=True)
        result_val_mass_change = sorted(result_val_mass_change[1:], key=lambda x: float(x[0]), reverse=True)

        # create dictionary with results
        dict_result = {"kJ/mol redox material": result_val_ener_i,
                       "kJ/kg redox material": result_val_per_kg_redox,
                       "Wh/kg redox material": result_val_per_kg_wh_redox,
                       str("kJ/mol of " + prodstr_alt): result_val_per_kj_mol_prod,
                       str("kJ/L of " + prodstr): result_val_per_energy_l,
                       str("Wh/L of " + prodstr): result_val_per_energy_l_wh,
                       "Heat to fuel efficiency in % (only valid for Water Splitting)": result_val_efficiency,
                       str("mol " + prodstr_alt + " per mol redox material"): result_val_mol_prod_mol_red,
                       str("L " + prodstr + " per mol redox material"): result_val_l_prod_kg_red,
                       str("g " + prodstr + " per mol redox material"): result_val_g_prod_kg_red,
                       "Change in non-stoichiometry between T_ox and T_red": result_val_delta_redox,
                       "Mass change between T_ox and T_red": result_val_mass_change
                       }

        return dict_result
