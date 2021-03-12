import numpy as np
from logic.pulsed.pulse_objects import PulseBlock, PulseBlockEnsemble
from logic.pulsed.pulse_objects import PredefinedGeneratorBase
from logic.pulsed.sampling_functions import SamplingFunctions


class PentaceneMethods(PredefinedGeneratorBase):
    """

    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


    def generate_podmr_pentacene(self, name='podmr_pen', freq_start=1430.0e6, freq_step=2e6, wait_2_time=50e-6,
                            num_of_points=20, alternating_no_mw=False):
        """

        """
        created_blocks = list()
        created_ensembles = list()
        created_sequences = list()

        # Create frequency array
        freq_array = freq_start + np.arange(num_of_points) * freq_step

        # create the elements
        waiting_element = self._get_idle_element(length=self.wait_time,
                                                 increment=0)
        laser_element = self._get_laser_gate_element(length=self.laser_length,
                                                     increment=0)
        waiting_afterMW_element = self._get_idle_element(length=wait_2_time,
                                                     increment=0)
        delay_element = self._get_delay_gate_element()

        # Create block and append to created_blocks list
        pulsedodmr_block = PulseBlock(name=name)

        for mw_freq in freq_array:
            pulsedodmr_block.append(waiting_element)

            mw_element = self._get_mw_element(length=self.rabi_period / 2,
                                              increment=0,
                                              amp=self.microwave_amplitude,
                                              freq=mw_freq,
                                              phase=0)
            pulsedodmr_block.append(mw_element)
            pulsedodmr_block.append(waiting_afterMW_element)
            pulsedodmr_block.append(laser_element)
            pulsedodmr_block.append(delay_element)
            if alternating_no_mw:
                pulsedodmr_block.append(waiting_element)
                no_mw_element = self._get_mw_element(length=self.rabi_period / 2,
                                                  increment=0,
                                                  amp=0,
                                                  freq=mw_freq/2.,
                                                  phase=0)
                pulsedodmr_block.append(no_mw_element)
                pulsedodmr_block.append(waiting_afterMW_element)
                pulsedodmr_block.append(laser_element)
                pulsedodmr_block.append(delay_element)
        created_blocks.append(pulsedodmr_block)

        # Create block ensemble
        block_ensemble = PulseBlockEnsemble(name=name, rotating_frame=False)
        block_ensemble.append((pulsedodmr_block.name, 0))

        # Create and append sync trigger block if needed
        self._add_trigger(created_blocks=created_blocks, block_ensemble=block_ensemble)

        # add metadata to invoke settings later on
        block_ensemble.measurement_information['alternating'] = alternating_no_mw
        block_ensemble.measurement_information['laser_ignore_list'] = list()
        block_ensemble.measurement_information['controlled_variable'] = freq_array
        block_ensemble.measurement_information['units'] = ('Hz', '')
        block_ensemble.measurement_information['labels'] = ('Frequency', 'Signal')
        block_ensemble.measurement_information['number_of_lasers'] = num_of_points
        block_ensemble.measurement_information['counting_length'] = self._get_ensemble_count_length(
            ensemble=block_ensemble, created_blocks=created_blocks)

        # append ensemble to created ensembles
        created_ensembles.append(block_ensemble)
        return created_blocks, created_ensembles, created_sequences

    def generate_fakecwodmr_pentacene(self, name='fake_cw_odmr_pen', freq_start=1430.0e6, freq_step=2e6, t_single=50e-6,
                                 num_of_points=20, alternating_no_mw=False):
        """

        """
        created_blocks = list()
        created_ensembles = list()
        created_sequences = list()

        # Create frequency array
        freq_array = freq_start + np.arange(num_of_points) * freq_step

        # create the elements
        waiting_element = self._get_idle_element(length=self.wait_time,
                                                 increment=0)
        delay_element = self._get_delay_gate_element()

        # Create block and append to created_blocks list
        pulsedodmr_block = PulseBlock(name=name)

        for mw_freq in freq_array:

            mw_element = self._get_mw_laser_element(length=t_single,
                                              increment=0,
                                              amp=self.microwave_amplitude,
                                              freq=mw_freq,
                                              phase=0)
            pulsedodmr_block.append(mw_element)
            pulsedodmr_block.append(delay_element)
            pulsedodmr_block.append(waiting_element)

            if alternating_no_mw:
                no_mw_element = self._get_mw_laser_element(length=t_single,
                                                     increment=0,
                                                     amp=0,
                                                     freq=mw_freq / 2.,
                                                     phase=0)
                pulsedodmr_block.append(no_mw_element)
                pulsedodmr_block.append(delay_element)
                pulsedodmr_block.append(waiting_element)

        created_blocks.append(pulsedodmr_block)

        # Create block ensemble
        block_ensemble = PulseBlockEnsemble(name=name, rotating_frame=False)
        block_ensemble.append((pulsedodmr_block.name, 0))

        # Create and append sync trigger block if needed
        self._add_trigger(created_blocks=created_blocks, block_ensemble=block_ensemble)

        # add metadata to invoke settings later on
        block_ensemble.measurement_information['alternating'] = alternating_no_mw
        block_ensemble.measurement_information['laser_ignore_list'] = list()
        block_ensemble.measurement_information['controlled_variable'] = freq_array
        block_ensemble.measurement_information['units'] = ('Hz', '')
        block_ensemble.measurement_information['labels'] = ('Frequency', 'Signal')
        block_ensemble.measurement_information['number_of_lasers'] = num_of_points
        block_ensemble.measurement_information['counting_length'] = self._get_ensemble_count_length(
            ensemble=block_ensemble, created_blocks=created_blocks)

        # append ensemble to created ensembles
        created_ensembles.append(block_ensemble)
        return created_blocks, created_ensembles, created_sequences

    def generate_rabi_pentacene(self, name='rabi_pen', tau_start=10.0e-9, tau_step=10.0e-9, num_of_points=50,
                                wait_2_time=50e-6, alternating_no_mw=False):
        """

        """
        created_blocks = list()
        created_ensembles = list()
        created_sequences = list()

        # get tau array for measurement ticks
        tau_array = tau_start + np.arange(num_of_points) * tau_step

        # create the laser_mw element
        mw_element = self._get_mw_element(length=tau_start,
                                          increment=tau_step,
                                          amp=self.microwave_amplitude,
                                          freq=self.microwave_frequency,
                                          phase=0)
        noMw_element = self._get_mw_element(length=tau_start,
                                          increment=tau_step,
                                          amp=0,
                                          freq=self.microwave_frequency/2,
                                          phase=0)

        waiting_element = self._get_idle_element(length=self.wait_time,
                                                         increment=0)
        waiting_element_after_mw = self._get_idle_element(length=wait_2_time,
                                                 increment=0)
        laser_element = self._get_laser_gate_element(length=self.laser_length,
                                                     increment=0)
        delay_element = self._get_delay_gate_element()

        # Create block and append to created_blocks list
        rabi_block = PulseBlock(name=name)
        rabi_block.append(waiting_element)
        rabi_block.append(mw_element)
        rabi_block.append(waiting_element_after_mw)
        rabi_block.append(laser_element)
        rabi_block.append(delay_element)
        if alternating_no_mw:
            rabi_block.append(waiting_element)
            rabi_block.append(noMw_element)
            rabi_block.append(waiting_element_after_mw)
            rabi_block.append(laser_element)
            rabi_block.append(delay_element)

        created_blocks.append(rabi_block)

        # Create block ensemble
        block_ensemble = PulseBlockEnsemble(name=name, rotating_frame=False)
        block_ensemble.append((rabi_block.name, num_of_points - 1))

        # Create and append sync trigger block if needed
        self._add_trigger(created_blocks=created_blocks, block_ensemble=block_ensemble)

        # add metadata to invoke settings later on
        block_ensemble.measurement_information['alternating'] = alternating_no_mw
        block_ensemble.measurement_information['laser_ignore_list'] = list()
        block_ensemble.measurement_information['controlled_variable'] = tau_array
        block_ensemble.measurement_information['units'] = ('s', '')
        block_ensemble.measurement_information['labels'] = ('Tau', 'Signal')
        block_ensemble.measurement_information['number_of_lasers'] = 2 * num_of_points if alternating_no_mw else num_of_points
        block_ensemble.measurement_information['counting_length'] = self._get_ensemble_count_length(
            ensemble=block_ensemble, created_blocks=created_blocks)

        # Append ensemble to created_ensembles list
        created_ensembles.append(block_ensemble)
        return created_blocks, created_ensembles, created_sequences

    def generate_rabi_NV_red_read(self, name='rabi_red', tau_start=10.0e-9, tau_step=10.0e-9, num_of_points=50,
                                 t_laser_init=10e-6, t_wait_between=10e-9, laser_read_ch='', add_gate_ch=''):
        """

        """
        created_blocks = list()
        created_ensembles = list()
        created_sequences = list()

        # get tau array for measurement ticks
        tau_array = tau_start + np.arange(num_of_points) * tau_step

        # create the laser_mw element
        mw_element = self._get_mw_element(length=tau_start,
                                          increment=tau_step,
                                          amp=self.microwave_amplitude,
                                          freq=self.microwave_frequency,
                                          phase=0)
        waiting_element = self._get_idle_element(length=self.wait_time,
                                                 increment=0)
        laser_red_element = self._get_laser_gate_element(length=self.laser_length,
                                                     increment=0)
        if laser_read_ch:
            laser_red_element.digital_high[self.laser_channel] = False
            laser_red_element.digital_high[laser_read_ch] = True

        # additional gate channel, independent on the one from pulsed gui
        if add_gate_ch:
            laser_red_element.digital_high[add_gate_ch] = True

        idle_between_lasers_element = self._get_idle_element(length=t_wait_between,
                                                 increment=0)
        laser_init_element = self._get_laser_gate_element(length=t_laser_init,
                                                     increment=0)
        delay_element = self._get_delay_gate_element()

        # Create block and append to created_blocks list
        rabi_block = PulseBlock(name=name)
        rabi_block.append(mw_element)
        rabi_block.append(laser_red_element)
        rabi_block.append(idle_between_lasers_element)
        rabi_block.append(laser_init_element)
        rabi_block.append(delay_element)
        rabi_block.append(waiting_element)
        created_blocks.append(rabi_block)

        # Create block ensemble
        block_ensemble = PulseBlockEnsemble(name=name, rotating_frame=False)
        block_ensemble.append((rabi_block.name, num_of_points - 1))

        # Create and append sync trigger block if needed
        self._add_trigger(created_blocks=created_blocks, block_ensemble=block_ensemble)

        # add metadata to invoke settings later on
        block_ensemble.measurement_information['alternating'] = False
        block_ensemble.measurement_information['laser_ignore_list'] = list()
        block_ensemble.measurement_information['controlled_variable'] = tau_array
        block_ensemble.measurement_information['units'] = ('s', '')
        block_ensemble.measurement_information['labels'] = ('Tau', 'Signal')
        block_ensemble.measurement_information['number_of_lasers'] = num_of_points
        block_ensemble.measurement_information['counting_length'] = self._get_ensemble_count_length(
            ensemble=block_ensemble, created_blocks=created_blocks)

        # Append ensemble to created_ensembles list
        created_ensembles.append(block_ensemble)
        return created_blocks, created_ensembles, created_sequences

    def generate_t1_pentacene(self, name='T1_pen', tau_start=1.0e-6, tau_step=1.0e-6,
                    num_of_points=50, alternating=False, wait_2_time=50e-6):
        """

        """
        created_blocks = list()
        created_ensembles = list()
        created_sequences = list()

        # get tau array for measurement ticks
        tau_array = tau_start + np.arange(num_of_points) * tau_step

        # create the elements
        waiting_element = self._get_idle_element(length=self.wait_time,
                                                 increment=0)
        waiting_element_after_mw = self._get_idle_element(length=wait_2_time,
                                                 increment=0)
        laser_element = self._get_laser_gate_element(length=self.laser_length,
                                                     increment=0)
        delay_element = self._get_delay_gate_element()
        if alternating:  # get pi element
            pi_element = self._get_mw_element(length=self.rabi_period / 2,
                                              increment=0,
                                              amp=self.microwave_amplitude,
                                              freq=self.microwave_frequency,
                                              phase=0)

        tau_element = self._get_idle_element(length=tau_start, increment=tau_step)
        t1_block = PulseBlock(name=name)
        t1_block.append(tau_element)
        t1_block.append(waiting_element_after_mw)
        t1_block.append(laser_element)
        t1_block.append(delay_element)
        t1_block.append(waiting_element)
        if alternating:
            t1_block.append(pi_element)
            t1_block.append(tau_element)
            t1_block.append(waiting_element_after_mw)
            t1_block.append(laser_element)
            t1_block.append(delay_element)
            t1_block.append(waiting_element)
        created_blocks.append(t1_block)

        # Create block ensemble
        block_ensemble = PulseBlockEnsemble(name=name, rotating_frame=False)
        block_ensemble.append((t1_block.name, num_of_points - 1))

        # Create and append sync trigger block if needed
        self._add_trigger(created_blocks=created_blocks, block_ensemble=block_ensemble)

        # add metadata to invoke settings later on
        number_of_lasers = 2 * num_of_points if alternating else num_of_points
        block_ensemble.measurement_information['alternating'] = alternating
        block_ensemble.measurement_information['laser_ignore_list'] = list()
        block_ensemble.measurement_information['controlled_variable'] = tau_array
        block_ensemble.measurement_information['units'] = ('s', '')
        block_ensemble.measurement_information['labels'] = ('Tau', 'Signal')
        block_ensemble.measurement_information['number_of_lasers'] = number_of_lasers
        block_ensemble.measurement_information['counting_length'] = self._get_ensemble_count_length(
            ensemble=block_ensemble, created_blocks=created_blocks)
        # append ensemble to created ensembles
        created_ensembles.append(block_ensemble)
        return created_blocks, created_ensembles, created_sequences

    def generate_laser_on_jump(self, name='laser_on_jump_off', length=10.0e-3, jump_channel='d_ch4'):

        created_blocks = list()
        created_ensembles = list()
        created_sequences = list()

        # create the laser element
        laser_element = self._get_laser_element(length=length, increment=0)

        # create the laser element with "jump" signal
        laser_element_jump = self._get_laser_element(length=length, increment=0)
        laser_element_jump.digital_high[jump_channel] = True

        waiting_element = self._get_idle_element(length=length/2.,
                                                increment=0)

        # Create block and append to created_blocks list
        laser_block = PulseBlock(name=name)
        laser_block.append(waiting_element)
        laser_block.append(laser_element)
        laser_block.append(laser_element_jump)
        laser_block.append(laser_element)
        laser_block.append(waiting_element)

        created_blocks.append(laser_block)

        # Create block ensemble and append to created_ensembles list
        block_ensemble = PulseBlockEnsemble(name=name, rotating_frame=False)
        block_ensemble.append((laser_block.name, 0))


        # Create and append sync trigger block if needed
        self._add_trigger(created_blocks=created_blocks, block_ensemble=block_ensemble)

        number_of_lasers = 1
        block_ensemble.measurement_information['alternating'] = False
        block_ensemble.measurement_information['laser_ignore_list'] = list()
        block_ensemble.measurement_information['controlled_variable'] = [0]
        block_ensemble.measurement_information['units'] = ('a.u.', '')
        block_ensemble.measurement_information['labels'] = ('data point', 'Signal')
        block_ensemble.measurement_information['number_of_lasers'] = number_of_lasers
        block_ensemble.measurement_information['counting_length'] = self._get_ensemble_count_length(
            ensemble=block_ensemble, created_blocks=created_blocks)

        created_ensembles.append(block_ensemble)
        return created_blocks, created_ensembles, created_sequences



    def generate_pol_ise_pentacene(self, name='pol_pen', t_laser=1e-6, t_mw_ramp=100e-9, f_mw_sweep=10e6,
                                   jump_channel='d_ch4'):

        created_blocks = list()
        created_ensembles = list()
        created_sequences = list()

        # create the laser element
        """
        laser_element = self._get_laser_element(length=t_laser, increment=0)

        # create the laser element with "jump" signal
        laser_element_jump = self._get_laser_element(length=t_laser, increment=0)
        laser_element_jump.digital_high[jump_channel] = True
        """
        # create n mw chirps
        n_mw_chirps = int(t_laser/t_mw_ramp)
        if t_laser % t_mw_ramp != 0.:
            self.log.warning("Laser not dividable by t_mw. Extending to: {} us".
                             format(n_mw_chirps*t_mw_ramp))
        mw_freq_center = self.microwave_frequency
        freq_range = f_mw_sweep
        mw_freq_start = mw_freq_center - freq_range / 2.
        mw_freq_end = mw_freq_center + freq_range / 2

        mw_sweep_element = self.self._get_mw_element_linearchirp(length=t_mw_ramp,
                                                          increment=0,
                                                          amplitude=self.microwave_amplitude,
                                                          start_freq=mw_freq_start,
                                                          stop_freq=mw_freq_end,
                                                          phase=0)
        mw_sweep_element.digital_high[self.laser_channel] = True
        mw_sweep_element.digital_high[jump_channel] = True

        # Create block and append to created_blocks list
        laser_block = PulseBlock(name=name)
        #laser_block.append(laser_element_jump)
        for i in range(n_mw_chirps):
            laser_block.append(mw_sweep_element)

        created_blocks.append(laser_block)

        # Create block ensemble and append to created_ensembles list
        block_ensemble = PulseBlockEnsemble(name=name, rotating_frame=False)
        block_ensemble.append((laser_block.name, 0))


        # Create and append sync trigger block if needed
        self._add_trigger(created_blocks=created_blocks, block_ensemble=block_ensemble)

        number_of_lasers = 1
        block_ensemble.measurement_information['alternating'] = False
        block_ensemble.measurement_information['laser_ignore_list'] = list()
        block_ensemble.measurement_information['controlled_variable'] = [0]
        block_ensemble.measurement_information['units'] = ('a.u.', '')
        block_ensemble.measurement_information['labels'] = ('data point', 'Signal')
        block_ensemble.measurement_information['number_of_lasers'] = number_of_lasers
        block_ensemble.measurement_information['counting_length'] = self._get_ensemble_count_length(
            ensemble=block_ensemble, created_blocks=created_blocks)

        created_ensembles.append(block_ensemble)
        return created_blocks, created_ensembles, created_sequences

    def generate_deer_ramsey(self, name='deer_ramsey', f_mw_penta=1.4e9, t_rabi_penta=100e-9,
                             tau_start=1.0e-6, tau_step=1.0e-6, num_of_points=50, alternating_mode='pentacene_pi_off'):


        created_blocks = list()
        created_ensembles = list()
        created_sequences = list()

        # get tau array for measurement ticks
        tau_array = (tau_start + np.arange(num_of_points) * tau_step) + t_rabi_penta / 2

        # create the elements
        waiting_element = self._get_idle_element(length=self.wait_time,
                                                 increment=0)
        laser_element = self._get_laser_gate_element(length=self.laser_length,
                                                     increment=0)
        delay_element = self._get_delay_gate_element()
        pihalf_element = self._get_mw_element(length=self.rabi_period / 4,
                                              increment=0,
                                              amp=self.microwave_amplitude,
                                              freq=self.microwave_frequency,
                                              phase=0)
        pi_pentacene_element = self._get_mw_element(length=t_rabi_penta / 2,
                                              increment=0,
                                              amp=self.microwave_amplitude,
                                              freq=f_mw_penta,
                                              phase=0)
        idle_pentacene_element = self._get_idle_element(length=t_rabi_penta / 2,
                                                        increment=0)

        # Use a 180 deg phase shiftet pulse as 3pihalf pulse if microwave channel is analog
        if self.microwave_channel.startswith('a'):
            pi3half_element = self._get_mw_element(length=self.rabi_period / 4,
                                                   increment=0,
                                                   amp=self.microwave_amplitude,
                                                   freq=self.microwave_frequency,
                                                   phase=180)
        else:
            pi3half_element = self._get_mw_element(length=3 * self.rabi_period / 4,
                                                   increment=0,
                                                   amp=self.microwave_amplitude,
                                                   freq=self.microwave_frequency,
                                                   phase=0)
        tau_element = self._get_idle_element(length=tau_start, increment=tau_step)

        # Create block and append to created_blocks list
        ramsey_block = PulseBlock(name=name)
        ramsey_block.append(pihalf_element)
        ramsey_block.append(pi_pentacene_element)
        ramsey_block.append(tau_element)
        ramsey_block.append(pihalf_element)
        ramsey_block.append(laser_element)
        ramsey_block.append(delay_element)
        ramsey_block.append(waiting_element)

        alternating = False
        if alternating_mode == 'nv_pi_3_2':
            ramsey_block.append(pihalf_element)
            ramsey_block.append(tau_element)
            ramsey_block.append(pi3half_element)
            ramsey_block.append(laser_element)
            ramsey_block.append(delay_element)
            ramsey_block.append(waiting_element)
            alternating = True
        elif alternating_mode == 'pentacene_pi_off':
            ramsey_block.append(pihalf_element)
            ramsey_block.append(tau_element)
            ramsey_block.append(idle_pentacene_element)
            ramsey_block.append(pihalf_element)
            ramsey_block.append(laser_element)
            ramsey_block.append(delay_element)
            ramsey_block.append(waiting_element)
            alternating = True

        created_blocks.append(ramsey_block)

        # Create block ensemble
        block_ensemble = PulseBlockEnsemble(name=name, rotating_frame=True)
        block_ensemble.append((ramsey_block.name, num_of_points - 1))

        # Create and append sync trigger block if needed
        self._add_trigger(created_blocks=created_blocks, block_ensemble=block_ensemble)

        # add metadata to invoke settings later on
        number_of_lasers = 2 * num_of_points if alternating else num_of_points
        block_ensemble.measurement_information['alternating'] = alternating
        block_ensemble.measurement_information['laser_ignore_list'] = list()
        block_ensemble.measurement_information['controlled_variable'] = tau_array
        block_ensemble.measurement_information['units'] = ('s', '')
        block_ensemble.measurement_information['labels'] = ('Tau', 'Signal')
        block_ensemble.measurement_information['number_of_lasers'] = number_of_lasers
        block_ensemble.measurement_information['counting_length'] = self._get_ensemble_count_length(
            ensemble=block_ensemble, created_blocks=created_blocks)

        # append ensemble to created ensembles
        created_ensembles.append(block_ensemble)
        return created_blocks, created_ensembles, created_sequences