# -*- coding: utf-8 -*-

"""
This file contains the Qudi Hardware module NICard class.

Qudi is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Qudi is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Qudi. If not, see <http://www.gnu.org/licenses/>.

Copyright (c) the Qudi Developers. See the COPYRIGHT.txt file at the
top-level directory of this distribution and at <https://github.com/Ulm-IQO/qudi/>
"""

import numpy as np
import re
import time

from collections import OrderedDict

import PyDAQmx as daq

from core.module import Base, ConfigOption
from interface.slow_counter_interface import SlowCounterInterface
from interface.slow_counter_interface import SlowCounterConstraints
from interface.slow_counter_interface import CountingMode
from interface.odmr_counter_interface import ODMRCounterInterface
from interface.confocal_scanner_interface import ConfocalScannerInterface
from interface.finite_counter_interface import FiniteCounterInterface
from interface.analogue_reader_interface import AnalogueReaderInterface
from interface.analogue_output_interface import AnalogueOutputInterface


class NationalInstrumentsXSeries(Base, SlowCounterInterface, ConfocalScannerInterface, ODMRCounterInterface,
                                 FiniteCounterInterface, AnalogueReaderInterface, AnalogueOutputInterface):
    """ A National Instruments device that can count and control microvave generators.

    !!!!!! NI USB 63XX, NI PCIe 63XX and NI PXIe 63XX DEVICES ONLY !!!!!!

    See [National Instruments X Series Documentation](@ref nidaq-x-series) for details.

    stable: Kay Jahnke, Alexander Stark

    Example config for copy-paste:

    nicard_6343:
        module.Class: 'national_instruments_x_series.NationalInstrumentsXSeries'
        photon_sources:
            - '/Dev1/PFI8'
        #    - '/Dev1/PFI9'
        clock_channel: '/Dev1/Ctr0'
        default_clock_frequency: 100 # optional, in Hz
        counter_channels:
            - '/Dev1/Ctr1'
        counter_ai_channels:
            - '/Dev1/AI0'
        default_scanner_clock_frequency: 100 # optional, in Hz
        scanner_clock_channel: '/Dev1/Ctr2'
        pixel_clock_channel: '/Dev1/PFI6'
        scanner_ao_channels:
            - '/Dev1/AO0'
            - '/Dev1/AO1'
            - '/Dev1/AO2'
            - '/Dev1/AO3'
        scanner_ai_channels:
            - '/Dev1/AI1'
        scanner_counter_channels:
            - '/Dev1/Ctr3'
        scanner_voltage_ranges:
            - [-10, 10]
            - [-10, 10]
            - [-10, 10]
            - [-10, 10]
        scanner_position_ranges:
            - [0e-6, 200e-6]
            - [0e-6, 200e-6]
            - [-100e-6, 100e-6]
            - [-10, 10]

        odmr_trigger_channel: '/Dev1/PFI7'

        gate_in_channel: '/Dev1/PFI9'
        default_samples_number: 50
        max_counts: 3e7
        read_write_timeout: 10
        counting_edge_rising: True

    """

    _modtype = 'NICard'
    _modclass = 'hardware'

    # device hardware limitations
    _max_frequency = ConfigOption("maximal_frequency", missing="error")
    _analogue_resolution = ConfigOption('analogue_resolution', 16, missing='warn')

    # config options
    _photon_sources = ConfigOption('photon_sources', missing='error')

    # slow counter
    _clock_channel = ConfigOption('clock_channel', missing='error')
    _default_clock_frequency = ConfigOption('default_clock_frequency', 100, missing='info')
    _counter_channels = ConfigOption('counter_channels', missing='error')
    _counter_ai_channels = ConfigOption('counter_ai_channels', [], missing='info')

    # confocal scanner
    _default_scanner_clock_frequency = ConfigOption(
        'default_scanner_clock_frequency', 100, missing='info')
    _scanner_clock_channel = ConfigOption('scanner_clock_channel', missing='warn')
    _finite_clock_frequency = ConfigOption('finite_clock_frequency', 100, missing='warn')
    _pixel_clock_channel = ConfigOption('pixel_clock_channel', None)
    _scanner_ao_channels = ConfigOption('scanner_ao_channels', missing='error')
    _scanner_ai_channels = ConfigOption('scanner_ai_channels', [], missing='info')
    _scanner_counter_channels = ConfigOption('scanner_counter_channels', [], missing='warn')
    _scanner_voltage_ranges = ConfigOption('scanner_voltage_ranges', missing='error')
    _scanner_position_ranges = ConfigOption('scanner_position_ranges', missing='error')

    # odmr
    _odmr_trigger_channel = ConfigOption('odmr_trigger_channel', missing='error')
    _odmr_trigger_line = ConfigOption('odmr_trigger_line', 'Dev1/port0/line0', missing='warn')
    _odmr_switch_line = ConfigOption('odmr_switch_line', 'Dev1/port0/line1', missing='warn')

    _gate_in_channel = ConfigOption('gate_in_channel', missing='error')
    # number of readout samples, mainly used for gated counter
    _default_samples_number = ConfigOption('default_samples_number', 50, missing='info')
    # used as a default for expected maximum counts
    _max_counts = ConfigOption('max_counts', default=3e7)
    # timeout for the Read or/and write process in s
    _RWTimeout = ConfigOption('read_write_timeout', default=10)
    _counting_edge_rising = ConfigOption('counting_edge_rising', default=True)
    _a_o_channels = ConfigOption('Analogue_output_channels', {}, missing='error')
    _a_o_ranges = ConfigOption('Analogue_output_ranges', {}, missing='error')
    _a_i_channels = ConfigOption('Analogue_input_channels', {}, missing='error')
    _a_i_ranges = ConfigOption('Analogue_input_ranges', {}, missing='error')
    _dummy_frequency = ConfigOption('dummy_frequency', 100, missing='error')
    _clock_channels = ConfigOption('clock_channels', [], missing='error')

    def on_activate(self):
        """ Starts up the NI Card at activation.
        """
        # the tasks used on that hardware device:
        self._counter_daq_tasks = []
        self._counter_analog_daq_task = None
        self._clock_daq_task = None
        self._scanner_clock_daq_task = None
        self._scanner_ao_task = None
        self._scanner_counter_daq_tasks = []
        self._analogue_input_daq_tasks = {}
        self._analogue_output_daq_tasks = {}
        self._line_length = None
        self._odmr_length = None

        self._gated_counter_daq_task = None
        self._scanner_analog_daq_task = None
        self._odmr_pulser_daq_task = None
        self._oversampling = 0
        self._lock_in_active = False

        self._analogue_input_samples = {}
        self._analogue_input_started = False
        self._analogue_output_clock_frequency = self._default_scanner_clock_frequency
        self._clock_daq_task_new = {}
        self._clock_frequency_new = {}
        self._clock_channel_new = {}
        self._analogue_input_channels = {}
        self._analogue_output_channels = {}
        self._ai_voltage_range = {}
        self._ao_voltage_range = {}
        for i in self._a_o_channels:
            for j in dict(i).items():
                self._analogue_output_channels[j[0]] = j[1]
        ao_list = []
        for i in self._a_o_ranges.keys():
            if i not in self._analogue_output_channels.keys():
                self.log.error("%s is not a possible axis.\n Therefore it is not possible to define "
                               "an analogue output range for it. The range will be omitted", i)
                continue
            vlow, vhigh = float(self._a_o_ranges[i][0]), float(self._a_o_ranges[i][1])
            if vlow < vhigh:
                self._ao_voltage_range[i] = [vlow, vhigh]
            else:
                self.log.warn('Configuration %s  of analogue output range for %s incorrect, taking [0 , '
                              '6.] instead.', self._ao_voltage_range[i], i)
                self._ao_voltage_range[i] = [0, 6.]
            ao_list.append(i)

        # check if all analogue input channels have a voltage range defined:
        for i in self._analogue_output_channels.keys():
            if i not in ao_list:
                self.log.error("%s channel has no analogue output range defined. Taking default [0,6.] instead.")
                self._ao_voltage_range["i"] = [0, 6.]

        pos_list = ["x", "y", "z", "a"]
        self._a_o_pos_ranges = dict()
        for i in range(len(self._scanner_position_ranges)):
            if pos_list[i] in self._analogue_output_channels and pos_list[i] in self._a_o_ranges:
                self._a_o_pos_ranges[pos_list[i]] = self._scanner_position_ranges[i]

        for i in self._a_i_channels:
            for j in i.items():
                self._analogue_input_channels[j[0]] = j[1]
        ai_list = []
        for i in self._a_i_ranges.keys():
            if i not in self._analogue_input_channels.keys():
                self.log.error("%s is not a possible axis.\n Therefore it is not possible to define "
                               "an analogue input range for it. The range will be omitted", i)
                continue
            vlow, vhigh = float(self._a_i_ranges[i][0]), float(self._a_i_ranges[i][1])
            if vlow < vhigh:
                self._ai_voltage_range[i] = [vlow, vhigh]
            else:
                self.log.warn('Configuration %s  of analogue input range for %s incorrect, taking [0 , '
                              '2.] instead.', self._a_i_ranges[i], i)
                self._ai_voltage_range[i] = [0, 2.]
            ai_list.append(i)

        # check if all analogue input channels have a voltage range defined:
        for i in self._analogue_input_channels.keys():
            if i not in ai_list:
                self.log.error("%s channel has no analogue input range defined. Taking default [0,2.] instead.", i)
                self._ai_voltage_range[i] = [0, 2.]

        # handle other the parameters given by the config
        self._current_position = np.zeros(len(self._scanner_ao_channels))

        if len(self._scanner_ao_channels) < len(self._scanner_voltage_ranges):
            self.log.error(
                'Specify at least as many scanner_voltage_ranges as scanner_ao_channels!')

        if len(self._scanner_ao_channels) < len(self._scanner_position_ranges):
            self.log.error(
                'Specify at least as many scanner_position_ranges as scanner_ao_channels!')

        if len(self._scanner_counter_channels) + len(self._scanner_ai_channels) < 1:
            self.log.error(
                'Specify at least one counter or analog input channel for the scanner!')

        # Analogue output is always needed and it does not interfere with the
        # rest, so start it always and leave it running
        if self._start_analog_output() < 0:
            self.log.error('Failed to start analog output.')
            raise Exception('Failed to start NI Card module due to analog output failure.')

    def on_deactivate(self):
        """ Shut down the NI card.
        """
        self.reset_hardware()

    # =================== General commands =================
    def get_maximum_clock_freq(self):
        """"Returns the maximally possible readout frequency of the analogue input device in Hz
        @return int: frequency """
        return self._max_frequency

    def get_analogue_resolution(self):
        """"Returns the resolution of the analog input of the NIDAQ in bits
        @return int: input bit resolution """
        return self._analogue_resolution

    # =================== SlowCounterInterface Commands ========================

    def get_constraints(self):
        """ Get hardware limits of NI device.

        @return SlowCounterConstraints: constraints class for slow counter

        FIXME: ask hardware for limits when module is loaded
        """
        constraints = SlowCounterConstraints()
        constraints.max_detectors = 4
        constraints.min_count_frequency = 1e-3
        constraints.max_count_frequency = 10e9
        constraints.counting_mode = [CountingMode.CONTINUOUS]
        return constraints

    def set_up_clock(self, clock_frequency=None, clock_channel=None, scanner=False, idle=False):
        """ Configures the hardware clock of the NiDAQ card to give the timing.

        @param float clock_frequency: if defined, this sets the frequency of
                                      the clock in Hz
        @param string clock_channel: if defined, this is the physical channel
                                     of the clock within the NI card.
        @param bool scanner: if set to True method will set up a clock function
                             for the scanner, otherwise a clock function for a
                             counter will be set.
        @param bool idle: set whether idle situation of the counter (where
                          counter is doing nothing) is defined as
                                True  = 'Voltage High/Rising Edge'
                                False = 'Voltage Low/Falling Edge'

        @return int: error code (0:OK, -1:error)
        """

        if not scanner and self._clock_daq_task is not None:
            self.log.error('Another counter clock is already running, close this one first.')
            return -1

        if scanner and self._scanner_clock_daq_task is not None:
            self.log.error('Another scanner clock is already running, close this one first.')
            return -1

        # Create handle for task, this task will generate pulse signal for
        # photon counting
        my_clock_daq_task = daq.TaskHandle()

        # assign the clock frequency, if given
        if clock_frequency is not None:
            if not scanner:
                self._clock_frequency = float(clock_frequency)
            else:
                self._scanner_clock_frequency = float(clock_frequency)
        else:
            if not scanner:
                self._clock_frequency = self._default_clock_frequency
            else:
                self._scanner_clock_frequency = self._default_scanner_clock_frequency

        # use the correct clock in this method
        if scanner:
            my_clock_frequency = self._scanner_clock_frequency * 2
        else:
            my_clock_frequency = self._clock_frequency * 2

        # assign the clock channel, if given
        if clock_channel is not None:
            if not scanner:
                self._clock_channel = clock_channel
            else:
                self._scanner_clock_channel = clock_channel

        # use the correct clock channel in this method
        if scanner:
            my_clock_channel = self._scanner_clock_channel
        else:
            my_clock_channel = self._clock_channel

        # check whether only one clock pair is available, since some NI cards
        # only one clock channel pair.
        if self._scanner_clock_channel == self._clock_channel:
            if not ((self._clock_daq_task is None) and (self._scanner_clock_daq_task is None)):
                self.log.error(
                    'Only one clock channel is available!\n'
                    'Another clock is already running, close this one first '
                    'in order to use it for your purpose!')
                return -1

        # Adjust the idle state if necessary
        my_idle = daq.DAQmx_Val_High if idle else daq.DAQmx_Val_Low
        try:
            # create task for clock
            task_name = 'ScannerClock' if scanner else 'CounterClock'
            daq.DAQmxCreateTask(task_name, daq.byref(my_clock_daq_task))

            # create a digital clock channel with specific clock frequency:
            daq.DAQmxCreateCOPulseChanFreq(
                # The task to which to add the channels
                my_clock_daq_task,
                # which channel is used?
                my_clock_channel,
                # Name to assign to task (NIDAQ uses by # default the physical channel name as
                # the virtual channel name. If name is specified, then you must use the name
                # when you refer to that channel in other NIDAQ functions)
                'Clock Producer',
                # units, Hertz in our case
                daq.DAQmx_Val_Hz,
                # idle state
                my_idle,
                # initial delay
                0,
                # pulse frequency, divide by 2 such that length of semi period = count_interval
                my_clock_frequency / 2,
                # duty cycle of pulses, 0.5 such that high and low duration are both
                # equal to count_interval
                0.5)

            # Configure Implicit Timing.
            # Set timing to continuous, i.e. set only the number of samples to
            # acquire or generate without specifying timing:
            daq.DAQmxCfgImplicitTiming(
                # Define task
                my_clock_daq_task,
                # Sample Mode: set the task to generate a continuous amount of running samples
                daq.DAQmx_Val_ContSamps,
                # buffer length which stores temporarily the number of generated samples
                1000)

            if scanner:
                self._scanner_clock_daq_task = my_clock_daq_task
                self._clock_channel_new["Scanner"] = self._scanner_clock_channel
            else:
                # actually start the preconfigured clock task
                daq.DAQmxStartTask(my_clock_daq_task)
                self._clock_daq_task = my_clock_daq_task
                self._clock_channel_new["Counter"] = self._clock_channel
        except:
            self.log.exception('Error while setting up clock.')
            return -1
        return 0

    def set_up_counter(self,
                       counter_channels=None,
                       sources=None,
                       clock_channel=None,
                       counter_buffer=None):
        """ Configures the actual counter with a given clock.

        @param list(str) counter_channels: optional, physical channel of the counter
        @param list(str) sources: optional, physical channel where the photons
                                  are to count from
        @param str clock_channel: optional, specifies the clock channel for the
                                  counter
        @param int counter_buffer: optional, a buffer of specified integer
                                   length, where in each bin the count numbers
                                   are saved.

        @return int: error code (0:OK, -1:error)
        """

        if self._clock_daq_task is None and clock_channel is None:
            self.log.error('No clock running, call set_up_clock before starting the counter.')
            return -1

        if len(self._counter_daq_tasks) > 0:
            self.log.error('Another counter is already running, close this one first.')
            return -1

        if counter_channels is not None:
            my_counter_channels = counter_channels
        else:
            my_counter_channels = self._counter_channels

        if sources is not None:
            my_photon_sources = sources
        else:
            my_photon_sources = self._photon_sources

        if clock_channel is not None:
            my_clock_channel = clock_channel
        else:
            my_clock_channel = self._clock_channel

        if len(my_photon_sources) < len(my_counter_channels):
            self.log.error('You have given {0} sources but {1} counting channels.'
                           'Please give an equal or greater number of sources.'
                           ''.format(len(my_photon_sources), len(my_counter_channels)))
            return -1

        try:
            for i, ch in enumerate(my_counter_channels):
                # This task will count photons with binning defined by the clock_channel
                task = daq.TaskHandle()  # Initialize a Task
                # Create task for the counter
                daq.DAQmxCreateTask('Counter{0}'.format(i), daq.byref(task))
                # Create a Counter Input which samples with Semi-Periods the Channel.
                # set up semi period width measurement in photon ticks, i.e. the width
                # of each pulse (high and low) generated by pulse_out_task is measured
                # in photon ticks.
                #   (this task creates a channel to measure the time between state
                #    transitions of a digital signal and adds the channel to the task
                #    you choose)
                daq.DAQmxCreateCISemiPeriodChan(
                    # define to which task to connect this function
                    task,
                    # use this counter channel
                    ch,
                    # name to assign to it
                    'Counter Channel {0}'.format(i),
                    # expected minimum count value
                    0,
                    # Expected maximum count value
                    self._max_counts / 2 / self._clock_frequency,
                    # units of width measurement, here photon ticks
                    daq.DAQmx_Val_Ticks,
                    # empty extra argument
                    '')

                # Set the Counter Input to a Semi Period input Terminal.
                # Connect the pulses from the counter clock to the counter channel
                daq.DAQmxSetCISemiPeriodTerm(
                    # The task to which to add the counter channel.
                    task,
                    # use this counter channel
                    ch,
                    # assign a named Terminal
                    my_clock_channel + 'InternalOutput')

                # Set a Counter Input Control Timebase Source.
                # Specify the terminal of the timebase which is used for the counter:
                # Define the source of ticks for the counter as self._photon_source for
                # the Scanner Task.
                daq.DAQmxSetCICtrTimebaseSrc(
                    # define to which task to connect this function
                    task,
                    # counter channel
                    ch,
                    # counter channel to output the counting results
                    my_photon_sources[i])

                # Configure Implicit Timing.
                # Set timing to continuous, i.e. set only the number of samples to
                # acquire or generate without specifying timing:
                daq.DAQmxCfgImplicitTiming(
                    # define to which task to connect this function
                    task,
                    # Sample Mode: Acquire or generate samples until you stop the task.
                    daq.DAQmx_Val_ContSamps,
                    # buffer length which stores  temporarily the number of generated samples
                    10000)

                # Set the Read point Relative To an operation.
                # Specifies the point in the buffer at which to begin a read operation.
                # Here we read most recent recorded samples:
                daq.DAQmxSetReadRelativeTo(
                    # define to which task to connect this function
                    task,
                    # Start reading samples relative to the last sample returned by the previously.
                    daq.DAQmx_Val_CurrReadPos)

                # Set the Read Offset.
                # Specifies an offset in samples per channel at which to begin a read
                # operation. This offset is relative to the location you specify with
                # RelativeTo. Here we set the Offset to 0 for multiple samples:
                daq.DAQmxSetReadOffset(task, 0)

                # Set Read OverWrite Mode.
                # Specifies whether to overwrite samples in the buffer that you have
                # not yet read. Unread data in buffer will be overwritten:
                daq.DAQmxSetReadOverWrite(
                    task,
                    daq.DAQmx_Val_DoNotOverwriteUnreadSamps)
                # add task to counter task list
                self._counter_daq_tasks.append(task)

                # Counter analog input task
                if len(self._counter_ai_channels) > 0:
                    atask = daq.TaskHandle()

                    daq.DAQmxCreateTask('CounterAnalogIn', daq.byref(atask))

                    daq.DAQmxCreateAIVoltageChan(
                        atask,
                        ', '.join(self._counter_ai_channels),
                        'Counter Analog In',
                        daq.DAQmx_Val_RSE,
                        -10,
                        10,
                        daq.DAQmx_Val_Volts,
                        ''
                    )
                    # Analog in channel timebase
                    daq.DAQmxCfgSampClkTiming(
                        atask,
                        my_clock_channel + 'InternalOutput',
                        self._clock_frequency,
                        daq.DAQmx_Val_Rising,
                        daq.DAQmx_Val_ContSamps,
                        int(self._clock_frequency * 5)
                    )
                    self._counter_analog_daq_task = atask
        except:
            self.log.exception('Error while setting up counting task.')
            return -1

        try:
            for i, task in enumerate(self._counter_daq_tasks):
                # Actually start the preconfigured counter task
                daq.DAQmxStartTask(task)
            if len(self._counter_ai_channels) > 0:
                daq.DAQmxStartTask(self._counter_analog_daq_task)
        except:
            self.log.exception('Error while starting Counter')
            try:
                self.close_counter()
            except:
                self.log.exception('Could not close counter after error')
            return -1
        return 0

    def get_counter_channels(self):
        """ Returns the list of counter channel names.

        @return tuple(str): channel names

        Most methods calling this might just care about the number of channels, though.
        """
        ch = self._counter_channels[:]
        ch.extend(self._counter_ai_channels)
        return ch

    def get_counter(self, samples=None):
        """ Returns the current counts per second of the counter.

        @param int samples: if defined, number of samples to read in one go.
                            How many samples are read per readout cycle. The
                            readout frequency was defined in the counter setup.
                            That sets also the length of the readout array.

        @return float [samples]: array with entries as photon counts per second
        """
        if len(self._counter_daq_tasks) < 1:
            self.log.error(
                'No counter running, call set_up_counter before reading it.')
            # in case of error return a lot of -1
            return np.ones((len(self.get_counter_channels()), samples), dtype=np.uint32) * -1

        if len(self._counter_ai_channels) > 0 and self._counter_analog_daq_task is None:
            self.log.error(
                'No counter analog input task running, call set_up_counter before reading it.')
            # in case of error return a lot of -1
            return np.ones((len(self.get_counter_channels()), samples), dtype=np.uint32) * -1

        if samples is None:
            samples = int(self._samples_number)
        else:
            samples = int(samples)
        try:
            # count data will be written here in the NumPy array of length samples
            count_data = np.empty((len(self._counter_daq_tasks), 2 * samples), dtype=np.uint32)

            # number of samples which were actually read, will be stored here
            n_read_samples = daq.int32()
            for i, task in enumerate(self._counter_daq_tasks):
                # read the counter value: This function is blocking and waits for the
                # counts to be all filled:
                daq.DAQmxReadCounterU32(
                    # read from this task
                    task,
                    # number of samples to read
                    2 * samples,
                    # maximal time out for the read process
                    self._RWTimeout,
                    # write the readout into this array
                    count_data[i],
                    # length of array to write into
                    2 * samples,
                    # number of samples which were read
                    daq.byref(n_read_samples),
                    # Reserved for future use. Pass NULL (here None) to this parameter
                    None)

            # Analog channels
            if len(self._counter_ai_channels) > 0:
                analog_data = np.full(
                    (len(self._counter_ai_channels), samples), 111, dtype=np.float64)

                analog_read_samples = daq.int32()

                daq.DAQmxReadAnalogF64(
                    self._counter_analog_daq_task,
                    samples,
                    self._RWTimeout,
                    daq.DAQmx_Val_GroupByChannel,
                    analog_data,
                    len(self._counter_ai_channels) * samples,
                    daq.byref(analog_read_samples),
                    None
                )
        except:
            self.log.exception(
                'Getting samples from counter failed.')
            # in case of error return a lot of -1
            return np.ones((len(self.get_counter_channels()), samples), dtype=np.uint32) * -1

        real_data = np.empty((len(self._counter_channels), samples), dtype=np.uint32)

        # add up adjoint pixels to also get the counts from the low time of
        # the clock:
        real_data = count_data[:, ::2]
        real_data += count_data[:, 1::2]

        all_data = np.full((len(self.get_counter_channels()), samples), 222, dtype=np.float64)
        # normalize to counts per second for counter channels
        all_data[0:len(real_data)] = np.array(real_data * self._clock_frequency, np.float64)

        if len(self._counter_ai_channels) > 0:
            all_data[-len(self._counter_ai_channels):] = analog_data

        return all_data

    def close_counter(self, scanner=False):
        """ Closes the counter or scanner and cleans up afterwards.

        @param bool scanner: specifies if the counter- or scanner- function
                             will be executed to close the device.
                                True = scanner
                                False = counter

        @return int: error code (0:OK, -1:error)
        """
        error = 0
        if scanner:
            for i, task in enumerate(self._scanner_counter_daq_tasks):
                try:
                    # stop the counter task
                    daq.DAQmxStopTask(task)
                    # after stopping delete all the configuration of the counter
                    daq.DAQmxClearTask(task)
                except:
                    self.log.exception('Could not close scanner counter.')
                    error = -1
            self._scanner_counter_daq_tasks = []
        else:
            for i, task in enumerate(self._counter_daq_tasks):
                try:
                    # stop the counter task
                    daq.DAQmxStopTask(task)
                    # after stopping delete all the configuration of the counter
                    daq.DAQmxClearTask(task)
                    # set the task handle to None as a safety
                except:
                    self.log.exception('Could not close counter.')
                    error = -1
            self._counter_daq_tasks = []

            if len(self._counter_ai_channels) > 0:
                try:
                    # stop the counter task
                    daq.DAQmxStopTask(self._counter_analog_daq_task)
                    # after stopping delete all the configuration of the counter
                    daq.DAQmxClearTask(self._counter_analog_daq_task)
                    # set the task handle to None as a safety
                except:
                    self.log.exception('Could not close counter analog channels.')
                    error = -1
                self._counter_analog_daq_task = None
        return error

    def close_clock(self, scanner=False):
        """ Closes the clock and cleans up afterwards.

        @param bool scanner: specifies if the counter- or scanner- function
                             should be used to close the device.
                                True = scanner
                                False = counter

        @return int: error code (0:OK, -1:error)
        """
        if scanner:
            my_task = self._scanner_clock_daq_task
        else:
            my_task = self._clock_daq_task
        try:
            # Stop the clock task:
            daq.DAQmxStopTask(my_task)

            # After stopping delete all the configuration of the clock:
            daq.DAQmxClearTask(my_task)

            # Set the task handle to None as a safety
            if scanner:
                self._scanner_clock_daq_task = None
                self._clock_channel_new.pop("Scanner")
            else:
                self._clock_daq_task = None
                self._clock_channel_new.pop("Counter")
        except:
            self.log.exception('Could not close clock.')
            return -1
        return 0

    # ================ End SlowCounterInterface Commands =======================

    # ================ ConfocalScannerInterface Commands =======================
    def reset_hardware(self):
        """ Resets the NI hardware, so the connection is lost and other
            programs can access it.

        @return int: error code (0:OK, -1:error)
        """
        retval = 0
        chanlist = [
            self._odmr_trigger_channel,
            self._clock_channel,
            self._scanner_clock_channel,
            self._gate_in_channel
        ]
        chanlist.extend(self._scanner_ao_channels)
        chanlist.extend(self._photon_sources)
        chanlist.extend(self._counter_channels)
        chanlist.extend(self._scanner_counter_channels)

        devicelist = []
        for channel in chanlist:
            if channel is None:
                continue
            match = re.match(
                '^/(?P<dev>[0-9A-Za-z\- ]+[0-9A-Za-z\-_ ]*)/(?P<chan>[0-9A-Za-z]+)',
                channel)
            if match:
                devicelist.append(match.group('dev'))
            else:
                self.log.error('Did not find device name in {0}.'.format(channel))
        for device in set(devicelist):
            self.log.info('Reset device {0}.'.format(device))
            try:
                daq.DAQmxResetDevice(device)
            except:
                self.log.exception('Could not reset NI device {0}'.format(device))
                retval = -1
        return retval

    def get_scanner_axes(self):
        """ Scanner axes depends on how many channels the analogue output task has.
        """
        if self._scanner_ao_task is None:
            self.log.error('Cannot get channel number, analog output task does not exist.')
            return []

        n_channels = daq.uInt32()
        daq.DAQmxGetTaskNumChans(self._scanner_ao_task, n_channels)
        possible_channels = ['x', 'y', 'z', 'a']

        return possible_channels[0:int(n_channels.value)]

    def get_scanner_count_channels(self):
        """ Return list of counter channels """
        ch = self._scanner_counter_channels[:]
        ch.extend(self._scanner_ai_channels)
        return ch

    def get_position_range(self):
        """ Returns the physical range of the scanner.

        @return float [4][2]: array of 4 ranges with an array containing lower
                              and upper limit. The unit of the scan range is
                              meters.
        """
        return self._scanner_position_ranges

    def set_position_range(self, myrange=None):
        """ Sets the physical range of the scanner.

        @param float [4][2] myrange: array of 4 ranges with an array containing
                                     lower and upper limit. The unit of the
                                     scan range is meters.

        @return int: error code (0:OK, -1:error)
        """
        if myrange is None:
            myrange = [[0, 1e-6], [0, 1e-6], [0, 1e-6], [0, 1e-6]]

        if not isinstance(myrange, (frozenset, list, set, tuple, np.ndarray,)):
            self.log.error('Given range is no array type.')
            return -1

        if len(myrange) != 4:
            self.log.error(
                'Given range should have dimension 4, but has {0:d} instead.'
                ''.format(len(myrange)))
            return -1

        for pos in myrange:
            if len(pos) != 2:
                self.log.error(
                    'Given range limit {1:d} should have dimension 2, but has {0:d} instead.'
                    ''.format(len(pos), pos))
                return -1
            if pos[0] > pos[1]:
                self.log.error(
                    'Given range limit {0:d} has the wrong order.'.format(pos))
                return -1

        self._scanner_position_ranges = myrange
        return 0

    def set_voltage_range(self, myrange=None):
        """ Sets the voltage range of the NI Card.

        @param float [n][2] myrange: array containing lower and upper limit

        @return int: error code (0:OK, -1:error)
        """
        n_ch = len(self.get_scanner_axes())
        if myrange is None:
            myrange = [[-10., 10.], [-10., 10.], [-10., 10.], [-10., 10.]][0:n_ch]

        if not isinstance(myrange, (frozenset, list, set, tuple, np.ndarray)):
            self.log.error('Given range is no array type.')
            return -1

        if len(myrange) != n_ch:
            self.log.error(
                'Given range should have dimension 2, but has {0:d} instead.'
                ''.format(len(myrange)))
            return -1

        for r in myrange:
            if r[0] > r[1]:
                self.log.error('Given range limit {0:d} has the wrong order.'.format(r))
                return -1

        self._scanner_voltage_ranges = myrange
        return 0

    def _start_analog_output(self):
        """ Starts or restarts the analog output.

        @return int: error code (0:OK, -1:error)
        """
        try:
            # If an analog task is already running, kill that one first
            if self._scanner_ao_task is not None:
                # stop the analog output task
                daq.DAQmxStopTask(self._scanner_ao_task)

                # delete the configuration of the analog output
                daq.DAQmxClearTask(self._scanner_ao_task)

                # set the task handle to None as a safety
                self._scanner_ao_task = None

            # initialize ao channels / task for scanner, should always be active.
            # Define at first the type of the variable as a Task:
            self._scanner_ao_task = daq.TaskHandle()

            # create the actual analog output task on the hardware device. Via
            # byref you pass the pointer of the object to the TaskCreation function:
            daq.DAQmxCreateTask('ScannerAO', daq.byref(self._scanner_ao_task))
            for n, chan in enumerate(self._scanner_ao_channels):
                # Assign and configure the created task to an analog output voltage channel.
                daq.DAQmxCreateAOVoltageChan(
                    # The AO voltage operation function is assigned to this task.
                    self._scanner_ao_task,
                    # use (all) scanner ao_channels for the output
                    chan,
                    # assign a name for that channel
                    'Scanner AO Channel {0}'.format(n),
                    # minimum possible voltage
                    self._scanner_voltage_ranges[n][0],
                    # maximum possible voltage
                    self._scanner_voltage_ranges[n][1],
                    # units is Volt
                    daq.DAQmx_Val_Volts,
                    # empty for future use
                    '')
        except:
            self.log.exception('Error starting analog output task.')
            return -1
        return 0

    def _stop_analog_output(self):
        """ Stops the analog output.

        @return int: error code (0:OK, -1:error)
        """
        if self._scanner_ao_task is None:
            return -1
        retval = 0
        try:
            # stop the analog output task
            daq.DAQmxStopTask(self._scanner_ao_task)
        except:
            self.log.exception('Error stopping analog output.')
            retval = -1
        try:
            daq.DAQmxSetSampTimingType(self._scanner_ao_task, daq.DAQmx_Val_OnDemand)
        except:
            self.log.exception('Error changing analog output mode.')
            retval = -1
        return retval

    def set_up_scanner_clock(self, clock_frequency=None, clock_channel=None):
        """ Configures the hardware clock of the NiDAQ card to give the timing.

        @param float clock_frequency: if defined, this sets the frequency of
                                      the clock
        @param string clock_channel: if defined, this is the physical channel
                                     of the clock

        @return int: error code (0:OK, -1:error)
        """
        # The clock for the scanner is created on the same principle as it is
        # for the counter. Just to keep consistency, this function is a wrapper
        # around the set_up_clock.
        return self.set_up_clock(
            clock_frequency=clock_frequency,
            clock_channel=clock_channel,
            scanner=True)

    def set_up_scanner(self,
                       counter_channels=None,
                       sources=None,
                       clock_channel=None,
                       scanner_ao_channels=None):
        """ Configures the actual scanner with a given clock.

        The scanner works pretty much like the counter. Here you connect a
        created clock with a counting task. That can be seen as a gated
        counting, where the counts where sampled by the underlying clock.

        @param list(str) counter_channels: this is the physical channel of the counter
        @param list(str) sources:  this is the physical channel where the photons are to count from
        @param string clock_channel: optional, if defined, this specifies the clock for the counter
        @param list(str) scanner_ao_channels: optional, if defined, this specifies
                                           the analog output channels

        @return int: error code (0:OK, -1:error)
        """
        retval = 0
        if self._scanner_clock_daq_task is None and clock_channel is None:
            self.log.error('No clock running, call set_up_clock before starting the counter.')
            return -1

        if counter_channels is not None:
            my_counter_channels = counter_channels
        else:
            my_counter_channels = self._scanner_counter_channels

        if sources is not None:
            my_photon_sources = sources
        else:
            my_photon_sources = self._photon_sources

        if clock_channel is not None:
            self._my_scanner_clock_channel = clock_channel
        else:
            self._my_scanner_clock_channel = self._scanner_clock_channel

        if scanner_ao_channels is not None:
            self._scanner_ao_channels = scanner_ao_channels
            retval = self._start_analog_output()

        if len(my_photon_sources) < len(my_counter_channels):
            self.log.error('You have given {0} sources but {1} counting channels.'
                           'Please give an equal or greater number of sources.'
                           ''.format(len(my_photon_sources), len(my_counter_channels)))
            return -1

        try:
            # Set the Sample Timing Type. Task timing to use a sampling clock:
            # specify how the Data of the selected task is collected, i.e. set it
            # now to be sampled on demand for the analog output, i.e. when
            # demanded by software.
            daq.DAQmxSetSampTimingType(self._scanner_ao_task, daq.DAQmx_Val_OnDemand)

            for i, ch in enumerate(my_counter_channels):
                # create handle for task, this task will do the photon counting for the
                # scanner.
                task = daq.TaskHandle()

                # actually create the scanner counting task
                daq.DAQmxCreateTask('ScannerCounter{0}'.format(i), daq.byref(task))

                # Create a Counter Input which samples with Semi Periods the Channel.
                # set up semi period width measurement in photon ticks, i.e. the width
                # of each pulse (high and low) generated by pulse_out_task is measured
                # in photon ticks.
                #   (this task creates a channel to measure the time between state
                #    transitions of a digital signal and adds the channel to the task
                #    you choose)
                daq.DAQmxCreateCISemiPeriodChan(
                    # The task to which to add the channels
                    task,
                    # use this counter channel
                    ch,
                    # name to assign to it
                    'Scanner Counter Channel {0}'.format(i),
                    # expected minimum value
                    0,
                    # Expected maximum count value
                    self._max_counts / self._scanner_clock_frequency,
                    # units of width measurement, here Timebase photon ticks
                    daq.DAQmx_Val_Ticks,
                    '')

                # Set the Counter Input to a Semi Period input Terminal.
                # Connect the pulses from the scanner clock to the scanner counter
                daq.DAQmxSetCISemiPeriodTerm(
                    # The task to which to add the counter channel.
                    task,
                    # use this counter channel
                    ch,
                    # assign a Terminal Name
                    self._my_scanner_clock_channel + 'InternalOutput')

                # Set a CounterInput Control Timebase Source.
                # Specify the terminal of the timebase which is used for the counter:
                # Define the source of ticks for the counter as self._photon_source for
                # the Scanner Task.
                daq.DAQmxSetCICtrTimebaseSrc(
                    # define to which task to# connect this function
                    task,
                    # counter channel to output the# counting results
                    ch,
                    # which channel to count
                    my_photon_sources[i])
                self._scanner_counter_daq_tasks.append(task)

            # Scanner analog input task
            if len(self._scanner_ai_channels) > 0:
                atask = daq.TaskHandle()

                daq.DAQmxCreateTask('ScanAnalogIn', daq.byref(atask))

                daq.DAQmxCreateAIVoltageChan(
                    atask,
                    ', '.join(self._scanner_ai_channels),
                    'Scan Analog In',
                    daq.DAQmx_Val_RSE,
                    -10,
                    10,
                    daq.DAQmx_Val_Volts,
                    ''
                )
                self._scanner_analog_daq_task = atask
        except:
            self.log.exception('Error while setting up scanner.')
            retval = -1

        return retval

    def scanner_set_position(self, x=None, y=None, z=None, a=None):
        """Move stage to x, y, z, a (where a is the fourth voltage channel).

        #FIXME: No volts
        @param float x: position in x-direction (volts)
        @param float y: position in y-direction (volts)
        @param float z: position in z-direction (volts)
        @param float a: position in a-direction (volts)

        @return int: error code (0:OK, -1:error)
        """

        if self.module_state() == 'locked':
            self.log.error('Another scan_line is already running, close this one first.')
            return -1

        if x is not None:
            if not (self._scanner_position_ranges[0][0] <= x <= self._scanner_position_ranges[0][1]):
                self.log.error('You want to set x out of range: {0:f}.'.format(x))
                return -1
            self._current_position[0] = np.float(x)

        if y is not None:
            if not (self._scanner_position_ranges[1][0] <= y <= self._scanner_position_ranges[1][1]):
                self.log.error('You want to set y out of range: {0:f}.'.format(y))
                return -1
            self._current_position[1] = np.float(y)

        if z is not None:
            if not (self._scanner_position_ranges[2][0] <= z <= self._scanner_position_ranges[2][1]):
                self.log.error('You want to set z out of range: {0:f}.'.format(z))
                return -1
            self._current_position[2] = np.float(z)

        if a is not None:
            if not (self._scanner_position_ranges[3][0] <= a <= self._scanner_position_ranges[3][1]):
                self.log.error('You want to set a out of range: {0:f}.'.format(a))
                return -1
            self._current_position[3] = np.float(a)

        # the position has to be a vstack
        my_position = np.vstack(self._current_position)

        # then directly write the position to the hardware
        try:
            self._write_scanner_ao(
                voltages=self._scanner_position_to_volt(my_position),
                start=True)
        except:
            return -1
        return 0

    def _write_scanner_ao(self, voltages, length=1, start=False):
        """Writes a set of voltages to the analog outputs.

        @param float[][n] voltages: array of n-part tuples defining the voltage
                                    points
        @param int length: number of tuples to write
        @param bool start: write immediately (True)
                           or wait for start of task (False)

        n depends on how many channels are configured for analog output
        """
        # Number of samples which were actually written, will be stored here.
        # The error code of this variable can be asked with .value to check
        # whether all channels have been written successfully.
        self._AONwritten = daq.int32()
        # write the voltage instructions for the analog output to the hardware
        daq.DAQmxWriteAnalogF64(
            # write to this task
            self._scanner_ao_task,
            # length of the command (points)
            length,
            # start task immediately (True), or wait for software start (False)
            start,
            # maximal timeout in seconds for# the write process
            self._RWTimeout,
            # Specify how the samples are arranged: each pixel is grouped by channel number
            daq.DAQmx_Val_GroupByChannel,
            # the voltages to be written
            voltages,
            # The actual number of samples per channel successfully written to the buffer
            daq.byref(self._AONwritten),
            # Reserved for future use. Pass NULL(here None) to this parameter
            None)
        return self._AONwritten.value

    def _scanner_position_to_volt(self, positions=None):
        """ Converts a set of position pixels to acutal voltages.

        @param float[][n] positions: array of n-part tuples defining the pixels

        @return float[][n]: array of n-part tuples of corresponding voltages

        The positions is typically a matrix like
            [[x_values], [y_values], [z_values], [a_values]]
            but x, xy, xyz and xyza are allowed formats.
        """

        if not isinstance(positions, (frozenset, list, set, tuple, np.ndarray,)):
            self.log.error('Given position list is no array type.')
            return np.array([np.NaN])

        vlist = []
        for i, position in enumerate(positions):
            vlist.append(
                (self._scanner_voltage_ranges[i][1] - self._scanner_voltage_ranges[i][0])
                / (self._scanner_position_ranges[i][1] - self._scanner_position_ranges[i][0])
                * (position - self._scanner_position_ranges[i][0])
                + self._scanner_voltage_ranges[i][0]
            )
        volts = np.vstack(vlist)

        for i, v in enumerate(volts):
            if v.min() < self._scanner_voltage_ranges[i][0] or v.max() > self._scanner_voltage_ranges[i][1]:
                self.log.error(
                    'Voltages ({0}, {1}) exceed the limit, the positions have to '
                    'be adjusted to stay in the given range.'.format(v.min(), v.max()))
                return np.array([np.NaN])
        return volts

    def get_scanner_position(self):
        """ Get the current position of the scanner hardware.

        @return float[]: current position in (x, y, z, a).
        """
        return self._current_position.tolist()

    def _set_up_line(self, length=100):
        """ Sets up the analog output for scanning a line.

        Connect the timing of the Analog scanning task with the timing of the
        counting task.

        @param int length: length of the line in pixel

        @return int: error code (0:OK, -1:error)
        """
        if len(self._scanner_counter_channels) > 0 and len(self._scanner_counter_daq_tasks) < 1:
            self.log.error('Configured counter is not running, cannot scan a line.')
            return np.array([[-1.]])

        if len(self._scanner_ai_channels) > 0 and self._scanner_analog_daq_task is None:
            self.log.error('Configured analog input is not running, cannot scan a line.')
            return -1

        self._line_length = length

        try:
            # Just a formal check whether length is not a too huge number
            if length < np.inf:
                # Configure the Sample Clock Timing.
                # Set up the timing of the scanner counting while the voltages are
                # being scanned (i.e. that you go through each voltage, which
                # corresponds to a position. How fast the voltages are being
                # changed is combined with obtaining the counts per voltage peak).
                daq.DAQmxCfgSampClkTiming(
                    # add to this task
                    self._scanner_ao_task,
                    # use this channel as clock
                    self._my_scanner_clock_channel + 'InternalOutput',
                    # Maximum expected clock frequency
                    self._scanner_clock_frequency,
                    # Generate sample on falling edge
                    daq.DAQmx_Val_Rising,
                    # generate finite number of samples
                    daq.DAQmx_Val_FiniteSamps,
                    # number of samples to generate
                    self._line_length)

            # Configure Implicit Timing for the clock.
            # Set timing for scanner clock task to the number of pixel.
            daq.DAQmxCfgImplicitTiming(
                # define task
                self._scanner_clock_daq_task,
                # only a limited number of# counts
                daq.DAQmx_Val_FiniteSamps,
                # count twice for each voltage +1 for safety
                self._line_length + 1)

            for i, task in enumerate(self._scanner_counter_daq_tasks):
                # Configure Implicit Timing for the scanner counting task.
                # Set timing for scanner count task to the number of pixel.
                daq.DAQmxCfgImplicitTiming(
                    # define task
                    task,
                    # only a limited number of counts
                    daq.DAQmx_Val_FiniteSamps,
                    # count twice for each voltage +1 for safety
                    2 * self._line_length + 1)

                # Set the Read point Relative To an operation.
                # Specifies the point in the buffer at which to begin a read operation,
                # here we read samples from beginning of acquisition and do not overwrite
                daq.DAQmxSetReadRelativeTo(
                    # define to which task to connect this function
                    task,
                    # Start reading samples relative to the last sample returned
                    # by the previous read
                    daq.DAQmx_Val_CurrReadPos)

                # Set the Read Offset.
                # Specifies an offset in samples per channel at which to begin a read
                # operation. This offset is relative to the location you specify with
                # RelativeTo. Here we do not read the first sample.
                daq.DAQmxSetReadOffset(
                    # connect to this task
                    task,
                    # Offset after which to read
                    1)

                # Set Read OverWrite Mode.
                # Specifies whether to overwrite samples in the buffer that you have
                # not yet read. Unread data in buffer will be overwritten:
                daq.DAQmxSetReadOverWrite(
                    task,
                    daq.DAQmx_Val_DoNotOverwriteUnreadSamps)

            # Analog channels
            if len(self._scanner_ai_channels) > 0:
                # Analog in channel timebase
                daq.DAQmxCfgSampClkTiming(
                    self._scanner_analog_daq_task,
                    self._scanner_clock_channel + 'InternalOutput',
                    self._scanner_clock_frequency,
                    daq.DAQmx_Val_Rising,
                    daq.DAQmx_Val_ContSamps,
                    self._line_length + 1
                )
        except:
            self.log.exception('Error while setting up scanner to scan a line.')
            return -1
        return 0

    def scan_line(self, line_path=None, pixel_clock=False):
        """ Scans a line and return the counts on that line.

        @param float[c][m] line_path: array of c-tuples defining the voltage points
            (m = samples per line)
        @param bool pixel_clock: whether we need to output a pixel clock for this line

        @return float[m][n]: m (samples per line) n-channel photon counts per second

        The input array looks for a xy scan of 5x5 points at the position z=-2
        like the following:
            [ [1, 2, 3, 4, 5], [1, 1, 1, 1, 1], [-2, -2, -2, -2] ]
        n is the number of scanner axes, which can vary. Typical values are 2 for galvo scanners,
        3 for xyz scanners and 4 for xyz scanners with a special function on the a axis.
        """
        if len(self._scanner_counter_channels) > 0 and len(self._scanner_counter_daq_tasks) < 1:
            self.log.error('Configured counter is not running, cannot scan a line.')
            return np.array([[-1.]])

        if len(self._scanner_ai_channels) > 0 and self._scanner_analog_daq_task is None:
            self.log.error('Configured analog input is not running, cannot scan a line.')
            return -1

        if not isinstance(line_path, (frozenset, list, set, tuple, np.ndarray,)):
            self.log.error('Given line_path list is not array type.')
            return np.array([[-1.]])
        try:
            # set task timing to use a sampling clock:
            # specify how the Data of the selected task is collected, i.e. set it
            # now to be sampled by a hardware (clock) signal.
            daq.DAQmxSetSampTimingType(self._scanner_ao_task, daq.DAQmx_Val_SampClk)
            self._set_up_line(np.shape(line_path)[1])
            line_volts = self._scanner_position_to_volt(line_path)
            # write the positions to the analog output
            written_voltages = self._write_scanner_ao(
                voltages=line_volts,
                length=self._line_length,
                start=False)

            # start the timed analog output task
            daq.DAQmxStartTask(self._scanner_ao_task)

            for i, task in enumerate(self._scanner_counter_daq_tasks):
                daq.DAQmxStopTask(task)

            daq.DAQmxStopTask(self._scanner_clock_daq_task)

            if pixel_clock and self._pixel_clock_channel is not None:
                daq.DAQmxConnectTerms(
                    self._scanner_clock_channel + 'InternalOutput',
                    self._pixel_clock_channel,
                    daq.DAQmx_Val_DoNotInvertPolarity)

            # start the scanner counting task that acquires counts synchronously
            for i, task in enumerate(self._scanner_counter_daq_tasks):
                daq.DAQmxStartTask(task)

            if len(self._scanner_ai_channels) > 0:
                daq.DAQmxStartTask(self._scanner_analog_daq_task)

            daq.DAQmxStartTask(self._scanner_clock_daq_task)

            for i, task in enumerate(self._scanner_counter_daq_tasks):
                # wait for the scanner counter to finish
                daq.DAQmxWaitUntilTaskDone(
                    # define task
                    task,
                    # Maximum timeout for the counter times the positions. Unit is seconds.
                    self._RWTimeout * 2 * self._line_length)

            # wait for the scanner clock to finish
            daq.DAQmxWaitUntilTaskDone(
                # define task
                self._scanner_clock_daq_task,
                # maximal timeout for the counter times the positions
                self._RWTimeout * 2 * self._line_length)

            # count data will be written here
            self._scan_data = np.empty(
                (len(self.get_scanner_count_channels()), 2 * self._line_length),
                dtype=np.uint32)

            # number of samples which were read will be stored here
            n_read_samples = daq.int32()
            for i, task in enumerate(self._scanner_counter_daq_tasks):
                # actually read the counted photons
                daq.DAQmxReadCounterU32(
                    # read from this task
                    task,
                    # read number of double the # number of samples
                    2 * self._line_length,
                    # maximal timeout for the read# process
                    self._RWTimeout,
                    # write into this array
                    self._scan_data[i],
                    # length of array to write into
                    2 * self._line_length,
                    # number of samples which were actually read
                    daq.byref(n_read_samples),
                    # Reserved for future use. Pass NULL(here None) to this parameter.
                    None)

                # stop the counter task
                daq.DAQmxStopTask(task)

            # Analog channels
            if len(self._scanner_ai_channels) > 0:
                self._analog_data = np.full(
                    (len(self._scanner_ai_channels), self._line_length + 1),
                    222,
                    dtype=np.float64)

                analog_read_samples = daq.int32()

                daq.DAQmxReadAnalogF64(
                    self._scanner_analog_daq_task,
                    self._line_length + 1,
                    self._RWTimeout,
                    daq.DAQmx_Val_GroupByChannel,
                    self._analog_data,
                    len(self._scanner_ai_channels) * (self._line_length + 1),
                    daq.byref(analog_read_samples),
                    None
                )

                daq.DAQmxStopTask(self._scanner_analog_daq_task)

            # stop the clock task
            daq.DAQmxStopTask(self._scanner_clock_daq_task)

            # stop the analog output task
            self._stop_analog_output()

            if pixel_clock and self._pixel_clock_channel is not None:
                daq.DAQmxDisconnectTerms(
                    self._scanner_clock_channel + 'InternalOutput',
                    self._pixel_clock_channel)

            # create a new array for the final data (this time of the length
            # number of samples):
            self._real_data = np.empty(
                (len(self._scanner_counter_channels), self._line_length),
                dtype=np.uint32)

            # add up adjoint pixels to also get the counts from the low time of
            # the clock:
            self._real_data = self._scan_data[:, ::2]
            self._real_data += self._scan_data[:, 1::2]

            all_data = np.full(
                (len(self.get_scanner_count_channels()), self._line_length), 2, dtype=np.float64)
            all_data[0:len(self._real_data)] = np.array(
                self._real_data * self._scanner_clock_frequency, np.float64)

            if len(self._scanner_ai_channels) > 0:
                all_data[len(self._scanner_counter_channels):] = self._analog_data[:, :-1]

            # update the scanner position instance variable
            self._current_position = np.array(line_path[:, -1])
        except:
            self.log.exception('Error while scanning line.')
            return np.array([[-1.]])
        # return values is a rate of counts/s
        return all_data.transpose()

    def close_scanner(self):
        """ Closes the scanner and cleans up afterwards.

        @return int: error code (0:OK, -1:error)
        """
        a = self._stop_analog_output()

        b = 0
        if len(self._scanner_ai_channels) > 0:
            try:
                # stop the counter task
                daq.DAQmxStopTask(self._scanner_analog_daq_task)
                # after stopping delete all the configuration of the counter
                daq.DAQmxClearTask(self._scanner_analog_daq_task)
                # set the task handle to None as a safety
                self._scanner_analog_daq_task = None
            except:
                self.log.exception('Could not close analog.')
                b = -1

        c = self.close_counter(scanner=True)
        return -1 if a < 0 or b < 0 or c < 0 else 0

    def close_scanner_clock(self):
        """ Closes the clock and cleans up afterwards.

        @return int: error code (0:OK, -1:error)
        """
        return self.close_clock(scanner=True)

    # ================ End ConfocalScannerInterface Commands ===================

    # ==================== ODMRCounterInterface Commands =======================
    def set_up_odmr_clock(self, clock_frequency=None, clock_channel=None):
        """ Configures the hardware clock of the NiDAQ card to give the timing.

        @param float clock_frequency: if defined, this sets the frequency of
                                      the clock
        @param string clock_channel: if defined, this is the physical channel
                                     of the clock

        @return int: error code (0:OK, -1:error)
        """

        return self.set_up_clock(
            clock_frequency=clock_frequency,
            clock_channel=clock_channel,
            scanner=True,
            idle=False)

    def set_up_odmr(self, counter_channel=None, photon_source=None,
                    clock_channel=None, odmr_trigger_channel=None):
        """ Configures the actual counter with a given clock.

        @param string counter_channel: if defined, this is the physical channel
                                       of the counter
        @param string photon_source: if defined, this is the physical channel
                                     where the photons are to count from
        @param string clock_channel: if defined, this specifies the clock for
                                     the counter
        @param string odmr_trigger_channel: if defined, this specifies the
                                            trigger output for the microwave

        @return int: error code (0:OK, -1:error)
        """
        if self._scanner_clock_daq_task is None and clock_channel is None:
            self.log.error('No clock running, call set_up_clock before starting the counter.')
            return -1
        if len(self._scanner_counter_daq_tasks) > 0:
            self.log.error('Another counter is already running, close this one first.')
            return -1
        if len(self._scanner_ai_channels) > 0 and self._scanner_analog_daq_task is not None:
            self.log.error('Another analog is already running, close this one first.')
            return -1

        if clock_channel is not None:
            my_clock_channel = clock_channel
        else:
            my_clock_channel = self._scanner_clock_channel

        if counter_channel is not None:
            my_counter_channel = counter_channel
        else:
            my_counter_channel = self._scanner_counter_channels[0]

        if photon_source is not None:
            my_photon_source = photon_source
        else:
            my_photon_source = self._photon_sources[0]

        # this task will count photons with binning defined by the clock_channel
        task = daq.TaskHandle()
        if len(self._scanner_ai_channels) > 0:
            atask = daq.TaskHandle()
        try:
            # create task for the counter
            daq.DAQmxCreateTask('ODMRCounter', daq.byref(task))
            if len(self._scanner_ai_channels) > 0:
                daq.DAQmxCreateTask('ODMRAnalog', daq.byref(atask))

            # set up semi period width measurement in photon ticks, i.e. the width
            # of each pulse (high and low) generated by pulse_out_task is measured
            # in photon ticks.
            #   (this task creates a channel to measure the time between state
            #    transitions of a digital signal and adds the channel to the task
            #    you choose)
            daq.DAQmxCreateCISemiPeriodChan(
                # define to which task to# connect this function
                task,
                # use this counter channel
                my_counter_channel,
                # name to assign to it
                'ODMR Counter',
                # Expected minimum count value
                0,
                # Expected maximum count value
                self._max_counts / self._scanner_clock_frequency,
                # units of width measurement, here photon ticks
                daq.DAQmx_Val_Ticks,
                '')

            # Analog task
            if len(self._scanner_ai_channels) > 0:
                daq.DAQmxCreateAIVoltageChan(
                    atask,
                    ', '.join(self._scanner_ai_channels),
                    'ODMR Analog',
                    daq.DAQmx_Val_RSE,
                    -10,
                    10,
                    daq.DAQmx_Val_Volts,
                    ''
                )

            # connect the pulses from the clock to the counter
            daq.DAQmxSetCIPulseWidthTerm(
                task,
                my_counter_channel,
                my_clock_channel + 'InternalOutput')

            # define the source of ticks for the counter as self._photon_source
            daq.DAQmxSetCICtrTimebaseSrc(
                task,
                my_counter_channel,
                my_photon_source)

            # start and stop pulse task to correctly initiate idle state high voltage.
            daq.DAQmxStartTask(self._scanner_clock_daq_task)
            # otherwise, it will be low until task starts, and MW will receive wrong pulses.
            daq.DAQmxStopTask(self._scanner_clock_daq_task)

            if self.lock_in_active:
                ptask = daq.TaskHandle()
                daq.DAQmxCreateTask('ODMRPulser', daq.byref(ptask))
                daq.DAQmxCreateDOChan(
                    ptask,
                    '{0:s}, {1:s}'.format(self._odmr_trigger_line, self._odmr_switch_line),
                    "ODMRPulserChannel",
                    daq.DAQmx_Val_ChanForAllLines)

                self._odmr_pulser_daq_task = ptask

            # connect the clock to the trigger channel to give triggers for the
            # microwave
            daq.DAQmxConnectTerms(
                self._scanner_clock_channel + 'InternalOutput',
                self._odmr_trigger_channel,
                daq.DAQmx_Val_DoNotInvertPolarity)
            self._scanner_counter_daq_tasks.append(task)
            if len(self._scanner_ai_channels) > 0:
                self._scanner_analog_daq_task = atask
        except:
            self.log.exception('Error while setting up ODMR scan.')
            return -1
        return 0

    def set_odmr_length(self, length=100):
        """ Sets up the trigger sequence for the ODMR and the triggered microwave.

        @param int length: length of microwave sweep in pixel

        @return int: error code (0:OK, -1:error)
        """
        if len(self._scanner_counter_channels) > 0 and len(self._scanner_counter_daq_tasks) < 1:
            self.log.error('No counter is running, cannot do ODMR without one.')
            return -1

        if len(self._scanner_ai_channels) > 0 and self._scanner_analog_daq_task is None:
            self.log.error('No analog task is running, cannot do ODMR without one.')
            return -1

        self._odmr_length = length
        try:
            # set timing for odmr clock task to the number of pixel.
            daq.DAQmxCfgImplicitTiming(
                # define task
                self._scanner_clock_daq_task,
                # only a limited number of counts
                daq.DAQmx_Val_FiniteSamps,
                # count twice for each voltage +1 for starting this task.
                # This first pulse will start the count task.
                self._odmr_length + 1)

            # set timing for odmr count task to the number of pixel.
            daq.DAQmxCfgImplicitTiming(
                # define task
                self._scanner_counter_daq_tasks[0],
                # only a limited number of counts
                daq.DAQmx_Val_ContSamps,
                # count twice for each voltage +1 for starting this task.
                # This first pulse will start the count task.
                2 * (self._odmr_length + 1))

            # read samples from beginning of acquisition, do not overwrite
            daq.DAQmxSetReadRelativeTo(
                self._scanner_counter_daq_tasks[0],
                daq.DAQmx_Val_CurrReadPos)

            # do not read first sample
            daq.DAQmxSetReadOffset(
                self._scanner_counter_daq_tasks[0],
                0)

            # unread data in buffer will be overwritten
            daq.DAQmxSetReadOverWrite(
                self._scanner_counter_daq_tasks[0],
                daq.DAQmx_Val_DoNotOverwriteUnreadSamps)

            # Analog
            if len(self._scanner_ai_channels) > 0:
                # Analog in channel timebase
                daq.DAQmxCfgSampClkTiming(
                    self._scanner_analog_daq_task,
                    self._scanner_clock_channel + 'InternalOutput',
                    self._scanner_clock_frequency,
                    daq.DAQmx_Val_Rising,
                    daq.DAQmx_Val_ContSamps,
                    self._odmr_length + 1
                )

            if self._odmr_pulser_daq_task:
                # pulser channel timebase
                daq.DAQmxCfgSampClkTiming(
                    self._odmr_pulser_daq_task,
                    self._scanner_clock_channel + 'InternalOutput',
                    self._scanner_clock_frequency,
                    daq.DAQmx_Val_Rising,
                    daq.DAQmx_Val_ContSamps,
                    self._odmr_length + 1
                )
        except:
            self.log.exception('Error while setting up ODMR counter.')
            return -1
        return 0

    @property
    def oversampling(self):
        return self._oversampling

    @oversampling.setter
    def oversampling(self, val):
        if not isinstance(val, (int, float)):
            self.log.error('oversampling has to be int of float.')
        else:
            self._oversampling = int(val)

    @property
    def lock_in_active(self):
        return self._lock_in_active

    @lock_in_active.setter
    def lock_in_active(self, val):
        if not isinstance(val, bool):
            self.log.error('lock_in_active has to be boolean.')
        else:
            self._lock_in_active = val
            if self._lock_in_active:
                self.log.warn('You just switched the ODMR counter to Lock-In-mode. \n'
                              'Please make sure you connected all triggers correctly:\n'
                              '  {0:s} is the microwave trigger channel\n'
                              '  {1:s} is the switching channel for the lock in\n'
                              ''.format(self._odmr_trigger_line, self._odmr_switch_line))

    def count_odmr(self, length=100):
        """ Sweeps the microwave and returns the counts on that sweep.

        @param int length: length of microwave sweep in pixel

        @return float[]: the photon counts per second
        """
        if len(self._scanner_counter_daq_tasks) < 1:
            self.log.error(
                'No counter is running, cannot scan an ODMR line without one.')
            return True, np.array([-1.])

        if len(self._scanner_ai_channels) > 0 and self._scanner_analog_daq_task is None:
            self.log.error('No analog task is running, cannot do ODMR without one.')
            return True, np.array([-1.])

        # check if length setup is correct, if not, adjust.
        if self._odmr_pulser_daq_task:
            odmr_length_to_set = length * self.oversampling * 2
        else:
            odmr_length_to_set = length

        if self.set_odmr_length(odmr_length_to_set) < 0:
            self.log.error('An error arose while setting the odmr lenth to {}.'.format(odmr_length_to_set))
            return True, np.array([-1.])

        try:
            # start the scanner counting task that acquires counts synchronously
            daq.DAQmxStartTask(self._scanner_counter_daq_tasks[0])
            if len(self._scanner_ai_channels) > 0:
                daq.DAQmxStartTask(self._scanner_analog_daq_task)
        except:
            self.log.exception('Cannot start ODMR counter.')
            return True, np.array([-1.])

        if self._odmr_pulser_daq_task:
            try:

                # The pulse pattern is an alternating 0 and 1 on the switching channel (line0),
                # while the first half of the whole microwave pulse is 1 and the other half is 0.
                # This way the beginning of the microwave has a rising edge.
                pulse_pattern = np.zeros(self.oversampling * 2, dtype=np.uint32)
                pulse_pattern[:self.oversampling] += 1
                pulse_pattern[::2] += 2

                daq.DAQmxWriteDigitalU32(self._odmr_pulser_daq_task,
                                         len(pulse_pattern),
                                         0,
                                         self._RWTimeout * self._odmr_length,
                                         daq.DAQmx_Val_GroupByChannel,
                                         pulse_pattern,
                                         None,
                                         None)

                daq.DAQmxStartTask(self._odmr_pulser_daq_task)
            except:
                self.log.exception('Cannot start ODMR pulser.')
                return True, np.array([-1.])

        try:
            daq.DAQmxStartTask(self._scanner_clock_daq_task)

            # wait for the scanner clock to finish
            daq.DAQmxWaitUntilTaskDone(
                # define task
                self._scanner_clock_daq_task,
                # maximal timeout for the counter times the positions
                self._RWTimeout * 2 * self._odmr_length)

            # count data will be written here
            odmr_data = np.full(
                (2 * self._odmr_length + 1,),
                222,
                dtype=np.uint32)

            # number of samples which were read will be stored here
            n_read_samples = daq.int32()

            # actually read the counted photons
            daq.DAQmxReadCounterU32(
                # read from this task
                self._scanner_counter_daq_tasks[0],
                # Read number of double the# number of samples
                2 * self._odmr_length + 1,
                # Maximal timeout for the read # process
                self._RWTimeout,
                # write into this array
                odmr_data,
                # length of array to write into
                2 * self._odmr_length + 1,
                # number of samples which were actually read
                daq.byref(n_read_samples),
                # Reserved for future use. Pass NULL (here None) to this parameter.
                None)

            # Analog
            if len(self._scanner_ai_channels) > 0:
                odmr_analog_data = np.full(
                    (len(self._scanner_ai_channels), self._odmr_length + 1),
                    222,
                    dtype=np.float64)

                analog_read_samples = daq.int32()

                daq.DAQmxReadAnalogF64(
                    self._scanner_analog_daq_task,
                    self._odmr_length + 1,
                    self._RWTimeout,
                    daq.DAQmx_Val_GroupByChannel,
                    odmr_analog_data,
                    len(self._scanner_ai_channels) * (self._odmr_length + 1),
                    daq.byref(analog_read_samples),
                    None
                )

            # stop the counter task
            daq.DAQmxStopTask(self._scanner_clock_daq_task)
            daq.DAQmxStopTask(self._scanner_counter_daq_tasks[0])
            if len(self._scanner_ai_channels) > 0:
                daq.DAQmxStopTask(self._scanner_analog_daq_task)
            if self._odmr_pulser_daq_task:
                daq.DAQmxStopTask(self._odmr_pulser_daq_task)

            # prepare array to return data
            all_data = np.full((len(self.get_odmr_channels()), length),
                               222,
                               dtype=np.float64)

            # create a new array for the final data (this time of the length
            # number of samples)
            real_data = np.zeros((self._odmr_length,), dtype=np.uint32)

            # add up adjoint pixels to also get the counts from the low time of
            # the clock:

            real_data += odmr_data[1:-1:2]
            real_data += odmr_data[:-1:2]

            if self._odmr_pulser_daq_task:
                differential_data = np.zeros((self.oversampling * length,), dtype=np.float64)

                differential_data += real_data[1::2]
                differential_data -= real_data[::2]
                differential_data = np.divide(differential_data, real_data[::2],
                                              np.zeros_like(differential_data),
                                              where=real_data[::2] != 0)

                all_data[0] = np.median(np.reshape(differential_data,
                                                   (-1, self.oversampling)),
                                        axis=1
                                        )

                if len(self._scanner_ai_channels) > 0:
                    for i, analog_data in enumerate(odmr_analog_data):
                        differential_data = np.zeros((self.oversampling * length,), dtype=np.float64)

                        differential_data += analog_data[1:-1:2]
                        differential_data -= analog_data[:-1:2]
                        differential_data = np.divide(differential_data, analog_data[:-1:2],
                                                      np.zeros_like(differential_data),
                                                      where=analog_data[:-1:2] != 0)

                        all_data[i + 1] = np.median(np.reshape(differential_data,
                                                               (-1, self.oversampling)),
                                                    axis=1
                                                    )

            else:
                all_data[0] = np.array(real_data * self._scanner_clock_frequency, np.float64)
                if len(self._scanner_ai_channels) > 0:
                    all_data[1:] = odmr_analog_data[:, :-1]

            return False, all_data
        except:
            self.log.exception('Error while counting for ODMR.')
            return True, np.full((len(self.get_odmr_channels()), 1), [-1.])

    def close_odmr(self):
        """ Closes the odmr and cleans up afterwards.

        @return int: error code (0:OK, -1:error)
        """
        retval = 0
        try:
            # disconnect the trigger channel
            daq.DAQmxDisconnectTerms(
                self._scanner_clock_channel + 'InternalOutput',
                self._odmr_trigger_channel)

        except:
            self.log.exception('Error while disconnecting ODMR clock channel.')
            retval = -1

        if len(self._scanner_ai_channels) > 0:
            try:
                # stop the counter task
                daq.DAQmxStopTask(self._scanner_analog_daq_task)
                # after stopping delete all the configuration of the counter
                daq.DAQmxClearTask(self._scanner_analog_daq_task)
                # set the task handle to None as a safety
                self._scanner_analog_daq_task = None
            except:
                self.log.exception('Could not close analog.')
                retval = -1

        if self._odmr_pulser_daq_task:
            try:
                # stop the pulser task
                daq.DAQmxStopTask(self._odmr_pulser_daq_task)
                # after stopping delete all the configuration of the pulser
                daq.DAQmxClearTask(self._odmr_pulser_daq_task)
                # set the task handle to None as a safety
                self._odmr_pulser_daq_task = None
            except:
                self.log.exception('Could not close pulser.')
                retval = -1

        retval = -1 if self.close_counter(scanner=True) < 0 or retval < 0 else 0
        return retval

    def get_odmr_channels(self):
        ch = [self._scanner_counter_channels[0]]
        ch.extend(self._scanner_ai_channels)
        return ch

    def close_odmr_clock(self):
        """ Closes the odmr and cleans up afterwards.

        @return int: error code (0:OK, -1:error)
        """
        return self.close_clock(scanner=True)

    # ================== End ODMRCounterInterface Commands ====================

    def get_status(self):
        """ Receives the current status of the Fast Counter and outputs it as
            return value.

        0 = unconfigured
        1 = idle
        2 = running
        3 = paused
        -1 = error state
        """
        if self._gated_counter_daq_task is None:
            return 0
        else:
            # return value represents a uint32 value, i.e.
            #   task_done = 0  => False, i.e. device is running
            #   task_done !=0  => True, i.e. device has stopped
            task_done = daq.bool32()

            ret_v = daq.DAQmxIsTaskDone(
                # task reference
                self._gated_counter_daq_task,
                # reference to bool value.
                daq.byref(task_done))

            if ret_v != 0:
                return ret_v

            if task_done.value() == 0:
                return 1
            else:
                return 2

    # ======================== Gated photon counting ==========================

    def set_up_gated_counter(self, buffer_length, read_available_samples=False):
        """ Initializes and starts task for external gated photon counting.

        @param int buffer_length: Defines how long the buffer to be filled with
                                  samples should be. If buffer is full, program
                                  crashes, so use upper bound. Some reference
                                  calculated with sample_rate (in Samples/second)
                                  divided by Buffer_size:
                                  sample_rate/Buffer_size =
                                      no rate     /  10kS,
                                      (0-100S/s)  /  10kS
                                      (101-10kS/s)/   1kS,
                                      (10k-1MS/s) / 100kS,
                                      (>1MS/s)    / 1Ms
        @param bool read_available_samples: if False, NiDaq waits for the
                                            sample you asked for to be in the
                                            buffer before, if True it returns
                                            what is in buffer until 'samples'
                                            is full
        """
        if self._gated_counter_daq_task is not None:
            self.log.error(
                'Another gated counter is already running, close this one first.')
            return -1

        try:
            # This task will count photons with binning defined by pulse task
            # Initialize a Task
            self._gated_counter_daq_task = daq.TaskHandle()
            daq.DAQmxCreateTask('GatedCounter', daq.byref(self._gated_counter_daq_task))

            # Set up pulse width measurement in photon ticks, i.e. the width of
            # each pulse generated by pulse_out_task is measured in photon ticks:
            daq.DAQmxCreateCIPulseWidthChan(
                # add to this task
                self._gated_counter_daq_task,
                # use this counter
                self._counter_channel,
                # name you assign to it
                'Gated Counting Task',
                # expected minimum value
                0,
                # expected maximum value
                self._max_counts,
                # units of width measurement,  here photon ticks.
                daq.DAQmx_Val_Ticks,
                # start pulse width measurement on rising edge
                self._counting_edge,
                '')

            # Set the pulses to counter self._counter_channel
            daq.DAQmxSetCIPulseWidthTerm(
                self._gated_counter_daq_task,
                self._counter_channel,
                self._gate_in_channel)

            # Set the timebase for width measurement as self._photon_source, i.e.
            # define the source of ticks for the counter as self._photon_source.
            daq.DAQmxSetCICtrTimebaseSrc(
                self._gated_counter_daq_task,
                self._counter_channel,
                self._photon_source)

            # set timing to continuous
            daq.DAQmxCfgImplicitTiming(
                # define to which task to connect this function.
                self._gated_counter_daq_task,
                # Sample Mode: set the task to generate a continuous amount of running samples
                daq.DAQmx_Val_ContSamps,
                # buffer length which stores temporarily the number of generated samples
                buffer_length)

            # Read samples from beginning of acquisition, do not overwrite
            daq.DAQmxSetReadRelativeTo(self._gated_counter_daq_task, daq.DAQmx_Val_CurrReadPos)

            # If this is set to True, then the NiDaq will not wait for the sample
            # you asked for to be in the buffer before read out but immediately
            # hand back all samples until samples is reached.
            if read_available_samples:
                daq.DAQmxSetReadReadAllAvailSamp(self._gated_counter_daq_task, True)

            # Do not read first sample:
            daq.DAQmxSetReadOffset(self._gated_counter_daq_task, 0)

            # Unread data in buffer is not overwritten
            daq.DAQmxSetReadOverWrite(
                self._gated_counter_daq_task,
                daq.DAQmx_Val_DoNotOverwriteUnreadSamps)
        except:
            self.log.exception('Error while setting up gated counting.')
            return -1
        return 0

    def start_gated_counter(self):
        """Actually start the preconfigured counter task

        @return int: error code (0:OK, -1:error)
        """
        if self._gated_counter_daq_task is None:
            self.log.error(
                'Cannot start Gated Counter Task since it is notconfigured!\n'
                'Run the set_up_gated_counter routine.')
            return -1

        try:
            daq.DAQmxStartTask(self._gated_counter_daq_task)
        except:
            self.log.exception('Error while starting up gated counting.')
            return -1
        return 0

    def get_gated_counts(self, samples=None, timeout=None, read_available_samples=False):
        """ Returns latest count samples acquired by gated photon counting.

        @param int samples: if defined, number of samples to read in one go.
                            How many samples are read per readout cycle. The
                            readout frequency was defined in the counter setup.
                            That sets also the length of the readout array.
        @param int timeout: Maximal timeout for the read process. Since nidaq
                            waits for all samples to be acquired, make sure
                            this is long enough.
        @param bool read_available_samples : if False, NiDaq waits for the
                                             sample you asked for to be in the
                                             buffer before, True it returns
                                             what is in buffer until 'samples'
                                             is full.
        """
        if samples is None:
            samples = int(self._samples_number)
        else:
            samples = int(samples)

        if timeout is None:
            timeout = self._RWTimeout

        # Count data will be written here
        _gated_count_data = np.empty([2, samples], dtype=np.uint32)

        # Number of samples which were read will be stored here
        n_read_samples = daq.int32()

        if read_available_samples:
            # If the task acquires a finite number of samples
            # and you set this parameter to -1, the function
            # waits for the task to acquire all requested
            # samples, then reads those samples.
            num_samples = -1
        else:
            num_samples = int(samples)
        try:
            daq.DAQmxReadCounterU32(
                # read from this task
                self._gated_counter_daq_task,
                # read number samples
                num_samples,
                # maximal timeout for the read process
                timeout,
                _gated_count_data[0],
                # write into this array
                # length of array to write into
                samples,
                # number of samples which were actually read.
                daq.byref(n_read_samples),
                # Reserved for future use. Pass NULL (here None) to this parameter
                None)

            # Chops the array or read sample to the length that it exactly returns
            # acquired data and not more
            if read_available_samples:
                return _gated_count_data[0][:n_read_samples.value], n_read_samples.value
            else:
                return _gated_count_data
        except:
            self.log.exception('Error while reading gated count data.')
            return np.array([-1])

    def stop_gated_counter(self):
        """Actually start the preconfigured counter task

        @return int: error code (0:OK, -1:error)
        """
        if self._gated_counter_daq_task is None:
            self.log.error(
                'Cannot stop Gated Counter Task since it is not running!\n'
                'Start the Gated Counter Task before you can actually stop it!')
            return -1
        try:
            daq.DAQmxStopTask(self._gated_counter_daq_task)
        except:
            self.log.exception('Error while stopping gated counting.')
            return -1
        return 0

    def close_gated_counter(self):
        """ Clear tasks, so that counters are not in use any more.

        @return int: error code (0:OK, -1:error)
        """
        retval = 0
        try:
            # stop the task
            daq.DAQmxStopTask(self._gated_counter_daq_task)
        except:
            self.log.exception('Error while closing gated counter.')
            retval = -1
        try:
            # clear the task
            daq.DAQmxClearTask(self._gated_counter_daq_task)
            self._gated_counter_daq_task = None
        except:
            self.log.exception('Error while clearing gated counter.')
            retval = -1
        return retval

    # ======================== Digital channel control ==========================

    def digital_channel_switch(self, channel_name, mode=True):
        """
        Switches on or off the voltage output (5V) of one of the digital channels, that
        can as an example be used to switch on or off the AOM driver or apply a single
        trigger for ODMR.
        @param str channel_name: Name of the channel which should be controlled
                                    for example ('/Dev1/PFI9')
        @param bool mode: specifies if the voltage output of the chosen channel should be turned on or off

        @return int: error code (0:OK, -1:error)
        """
        if channel_name is None:
            self.log.error('No channel for digital output specified')
            return -1
        else:

            self.digital_out_task = daq.TaskHandle()
            if mode:
                self.digital_data = daq.c_uint32(0xffffffff)
            else:
                self.digital_data = daq.c_uint32(0x0)
            self.digital_read = daq.c_int32()
            self.digital_samples_channel = daq.c_int32(1)
            daq.DAQmxCreateTask('DigitalOut', daq.byref(self.digital_out_task))
            daq.DAQmxCreateDOChan(self.digital_out_task, channel_name, "", daq.DAQmx_Val_ChanForAllLines)
            daq.DAQmxStartTask(self.digital_out_task)
            daq.DAQmxWriteDigitalU32(self.digital_out_task, self.digital_samples_channel, True,
                                     self._RWTimeout, daq.DAQmx_Val_GroupByChannel,
                                     np.array(self.digital_data), self.digital_read, None)

            daq.DAQmxStopTask(self.digital_out_task)
            daq.DAQmxClearTask(self.digital_out_task)
            return 0

    # ================ FiniteCounterInterface Commands =======================

    def set_up_finite_counter(self, samples,
                              counter_channel=None,
                              photon_source=None,
                              clock_channel=None):
        """ Initializes task for counting a certain number of samples with given
        frequency. This ensures a hand waving synch between the counter and other devices.

        It works pretty much like the normal counter. Here you connect a
        created clock with a counting task. However here you only count for a predefined
        amount of time that is given by samples*frequency. The counts are sampled by
        the underlying clock.

        @param int samples: Defines how many counts should be gathered within one period
        @param string counter_channel: if defined, this is the physical channel
                                       of the counter
        @param string photon_source: if defined, this is the physical channel
                                     from where the photons are to be counted
        @param string clock_channel: if defined, this specifies the clock for
                                     the counter

        @return int:  error code (0: OK, -1:error)
        """

        if self._scanner_clock_daq_task is None and clock_channel is None:
            self.log.error('No clock running, call set_up_clock before starting the counter.')
            return -1
        if len(self._scanner_counter_daq_tasks) > 0:
            self.log.error('Another counter is already running, close this one first.')
            return -1

        if clock_channel is not None:
            my_clock_channel = clock_channel
        else:
            my_clock_channel = self._scanner_clock_channel

        if counter_channel is not None:
            my_counter_channel = counter_channel
        else:
            my_counter_channel = self._scanner_counter_channels[0]

        if photon_source is not None:
            my_photon_source = photon_source
        else:
            my_photon_source = self._photon_sources[0]

        # value defined for readout and wait until done
        self._finite_counter_samples = samples

        try:
            # This task will count photons with binning defined a clock
            # Initialize a Task
            task = daq.TaskHandle()
            daq.DAQmxCreateTask('FiniteCounter', daq.byref(task))

            # Set up pulse width measurement in photon ticks, i.e. the width of
            # each pulse generated by pulse_out_task is measured in photon ticks:
            daq.DAQmxCreateCIPulseWidthChan(
                # define to which task to connect this function
                task,
                # use this counter channel
                my_counter_channel,
                # name to assign to it
                'Finite Length Counter',
                # expected minimum count value
                0,
                # Expected maximum count value
                self._max_counts / 2 / self._finite_clock_frequency,
                # units of width measurement, here photon ticks
                daq.DAQmx_Val_Ticks,
                # must be None unless units is set to "DAQmx_Val_FromCustomScale",
                # start pulse width measurement on rising edge
                daq.DAQmx_Val_Rising,
                None)

            # Set the Counter Input to a Semi Period input Terminal.
            # Connect the pulses from the finite clock to the finite counter
            daq.DAQmxSetCIPulseWidthTerm(
                # The task to which to add the counter channel.
                task,
                # use this counter channel
                my_counter_channel,
                # assign a Terminal Name
                my_clock_channel + 'InternalOutput')

            # Set a Counter Input Control Timebase Source.
            # Specify the terminal of the timebase which is used for the counter:
            # Define the source of ticks for the counter as self._photon_source for
            # the Scanner Task.
            daq.DAQmxSetCICtrTimebaseSrc(
                # define to which task to connect this function
                task,
                # counter channel
                my_counter_channel,
                # counter channel to output the counting results
                my_photon_source)

            # Configure Implicit Timing.
            # Set timing to finite amount of sample:
            daq.DAQmxCfgImplicitTiming(
                # define to which task to connect this function
                task,
                # Sample Mode: set the task to read a specified number of samples
                daq.DAQmx_Val_FiniteSamps,
                # the specified number of samples to read
                samples)
            self._scanner_counter_daq_tasks.append(task)
        except:
            self.log.exception('Error while setting up finite counting.')
            return -1
        return 0

    def set_up_finite_counter_clock(self, clock_frequency=None, clock_channel=None):
        """ Configures the hardware clock of the NiDAQ card to give the timing.

        @param float clock_frequency: if defined, this sets the frequency of
                                      the clock (in Hz)
        @param string clock_channel: if defined, this is the physical channel
                                     of the clock

        @return int: error code (0:OK, -1:error)
        """
        # The clock for the finite_counter is created on the same principle as it is
        # for the counter. Just to keep consistency, this function is a wrapper
        # around the set_up_clock.
        channel = "Scanner_clock"
        if clock_frequency is None:
            clock_frequency = self._finite_clock_frequency
        else:
            self._finite_clock_frequency = clock_frequency

        # use the correct clock channel in this method
        # Todo: this has to be done like in new clock normally .
        # The way it is done here is just so it works with confocal
        if clock_channel is None:
            clock_channel = self._scanner_clock_channel

        # check whether only one clock pair is available, since some NI cards
        # only one clock channel pair.
        if self._scanner_clock_channel == self._clock_channel:
            if not ((self._clock_daq_task is None) and (self._scanner_clock_daq_task is None)):
                self.log.error(
                    'Only one clock channel is available!\n'
                    'Another clock is already running, close this one first '
                    'in order to use it for your purpose!')
                return -1

        if self._scanner_clock_daq_task is not None:
            self.log.error('Another scanner clock is already running, close this one first.')
            return -1
        # Todo: Check if this divided by 2 is sensible
        retval = self.set_up_clock_new(channel,
                                       clock_frequency=clock_frequency,
                                       clock_channel=clock_channel)

        if retval == 0:
            # Todo: This is a hot fix. It only makes sense to fix this when NIDAQ is rewritten completely
            self._scanner_clock_daq_task = self._clock_daq_task_new[channel]
            self._scanner_clock_frequency = self._clock_frequency_new[channel]
            self._scanner_clock_channel = self._clock_channel_new[channel]
            return 0
        else:
            return retval

    def start_finite_counter(self, start_clock=False):
        """Start the preconfigured counter task
        @param  bool start_clock: default value false, bool that defines if clock for the task is
                                started as well

        @return int: error code (0:OK, -1:error)
        """
        if self._scanner_counter_daq_tasks is None:
            self.log.error(
                'Cannot start Finite Counter Task since it is not configured!\n'
                'Run the set_up_finite_counter routine.')
            return -1
        elif len(self._scanner_counter_daq_tasks) > 1:
            self.log.error('To many (%s) Scanner Counter Tasks defined. Close all scanner '
                           'counters. \n Then re-setup the finite counter. ', len(self._scanner_counter_daq_tasks))
            return -1

        if start_clock:
            try:
                daq.DAQmxStopTask(self._scanner_clock_daq_task)
            except:
                self.log.warning('Error while stopping scanner clock counting')

            try:
                daq.DAQmxStartTask(self._scanner_clock_daq_task)
            except:
                self.log.error('Error while starting up finite counter clock')
                return -1

        for task in self._scanner_counter_daq_tasks:
            try:
                daq.DAQmxStartTask(task)
            except:
                self.log.exception('Error while starting up finite counting.')
                return -1
        return 0

    def get_finite_counts(self):
        """ Returns latest count samples acquired by finite photon counting.

        @return np.array, samples:The photon counts per second and the amount of samples read. For
        error array with length 1 and entry -1
        """
        if len(self._scanner_counter_daq_tasks) < 1:
            self.log.error(
                'No counter is running, cannot read counts line without one.')
            return np.array([-1.])
        if self._finite_counter_samples is None:
            self.log.error("No finite counter samples specified. Redo setup of counter")
            return np.array([-1])

        # *1.1 to have an extra (10%) short waiting time.
        timeout = (self._finite_counter_samples * 1.1) / self._finite_clock_frequency

        # Count data will be written here
        _finite_count_data = np.zeros((self._finite_counter_samples), dtype=np.uint32)

        # Number of samples which were read will be stored here
        n_read_samples = daq.int32()

        for task in self._scanner_counter_daq_tasks:
            try:
                daq.DAQmxReadCounterU32(
                    # read from this task
                    task,
                    # wait till all finite counts are acquired then return
                    -1,
                    # maximal timeout for the read process
                    timeout,
                    # write into this array
                    _finite_count_data,
                    # length of array to write into
                    self._finite_counter_samples,
                    # number of samples which were actually read.
                    daq.byref(n_read_samples),
                    # Reserved for future use. Pass NULL (here None) to this parameter
                    None)
            except:
                self.log.error("not able to read counts for finite counter.")
                return np.array([-1]), 0

        return self._finite_clock_frequency * _finite_count_data, n_read_samples.value  # counts per second

    def stop_finite_counter(self):
        """Stops the preconfigured counter task

        @return int: error code (0:OK, -1:error)
        """
        # check if task exists
        if len(self._scanner_counter_daq_tasks) < 1:
            self.log.error(
                'Cannot stop Finite Counter Task since it is not running or configured!\n'
                'Start the Counter Task Task before you can actually stop it!')
            return -1
        # check if samples for task were specified
        if self._finite_counter_samples is None:
            self.log.error("No finite counter samples specified.")
            return -1
        for task in self._scanner_counter_daq_tasks:
            # stop task for every existing scanner task
            try:
                daq.DAQmxStopTask(task)
            except:
                self.log.exception('Error while stopping finite counting.')
                return -1
            return 0

    def close_finite_counter(self):
        """ Clear tasks, so that counters are not in use any more.

        @return int: error code (0:OK, -1:error)
        """
        # erase sample value
        self._finite_counter_samples = None
        return self.close_counter(scanner=True)

    def close_finite_counter_clock(self):
        """ Closes the finite counter clock and cleans up afterwards.

        @return int: error code (0:OK, -1:error)
        """
        retval = self.close_clock_new("Scanner_clock")
        if retval == 0:
            self._scanner_clock_daq_task = None
        else:
            return retval

    # ================ End FiniteCounterInterface Commands =======================

    # ================ Start AnalogReaderInterface Commands  =======================

    def set_up_analogue_voltage_reader(self, analogue_channel):
        """Initializes task for reading a single analogue input voltage.

        @param string analogue_channel: the representative name of the analogue channel for
                                        which the task is created

        @return int: error code (0:OK, -1:error)
        """
        if analogue_channel in self._analogue_input_channels.keys():
            channel = self._analogue_input_channels[analogue_channel]
        else:
            self.log.error("The given analogue input channel %s is not defined. Please define the "
                           "input channel", analogue_channel)
            return -1

        if analogue_channel in self._analogue_input_daq_tasks:
            self.log.error('The same analogue input task is already running, close this one '
                           'first.')
            return -1
        # value defined for readout and wait until done
        self._analogue_input_samples[analogue_channel] = 1
        try:
            # This task will read an analogue voltage with binning defined by a clock
            # Initialize a Task
            task = daq.TaskHandle()
            daq.DAQmxCreateTask('Analogue Input {}'.format(analogue_channel), daq.byref(task))

            # Creates a channel to measure a voltage and adds it to task:
            daq.DAQmxCreateAIVoltageChan(
                # define to which task to connect this function
                task,
                # use this analogue input channel
                self._analogue_input_channels[analogue_channel],
                # name to assign to it
                "Analogue Voltage Reader {}".format(analogue_channel),
                # the analogue input read mode (rse, nres or diff)
                daq.DAQmx_Val_RSE,
                # the minimum input voltage expected
                self._ai_voltage_range[analogue_channel][0],
                # the minimum input voltage expected
                self._ai_voltage_range[analogue_channel][1],  # Todo: check type
                # the units in which the voltage is to be measured is volt
                daq.DAQmx_Val_Volts,
                # must be None unless units is set to "DAQmx_Val_FromCustomScale"
                None)
            self._analogue_input_daq_tasks[analogue_channel] = task
            self._analogue_input_samples[analogue_channel] = 1
        except:
            self.log.exception('Error while setting up analogue voltage reader for channel '
                               '{}.'.format(analogue_channel))
            return -1
        return 0

    def set_up_analogue_voltage_reader_scanner(self, samples,
                                               analogue_channel):
        """Initializes task for reading an analogue input voltage with the Nidaq for a finite
        number of samples at a given frequency.

        It reads a differentially connected voltage from the analogue inputs. For every period of
        time (given by the frequency) it reads the voltage at the analogue channel.

        @param int samples: Defines how many values are to be measured, minimum 2
        @param string analogue_channel: the representative name of the analogue channel for
                                        which the task is created

        @return int: error code (0:OK, -1:error)
        """
        if analogue_channel not in self._analogue_input_channels.keys():
            self.log.error("The given analogue input channel %s is not defined. Please define the "
                           "input channel", analogue_channel)
            return -1

        if analogue_channel not in self._clock_daq_task_new:
            self.log.error('No clock running, call set_up_clock before starting the analogue '
                           'reader.')
            return -1

        if analogue_channel in self._analogue_input_daq_tasks:
            self.log.error('An analogue input task for this channel is already running, '
                           'close this one first.')
            return -1

        if analogue_channel not in self._clock_channel_new:
            self.log.error("The clock channel for this task %s is not defined.", analogue_channel)
            return -1

        elif samples < 2:
            self.log.error(" The minimum amount of samples is 2. A value lower than 2 was choosen. ")
            return -1

        my_clock_channel = self._clock_channel_new[analogue_channel]

        # Fixme: Is this sensible?
        if analogue_channel not in self._clock_frequency_new:
            self.log.error("The clock frequency for this task %s is not defined.", analogue_channel)
            return -1
        # Todo: Fins usage of analogue clock frequency.
        clock_frequency = self._clock_frequency_new[analogue_channel]

        # value defined for readout and wait until done
        try:
            # This task will read an analogue voltage with binning defined by a clock
            # Initialize a Task
            task = daq.TaskHandle()
            daq.DAQmxCreateTask('Analogue Input {}'.format(analogue_channel), daq.byref(task))

            # Creates a channel to measure a voltage and adds it to task:
            daq.DAQmxCreateAIVoltageChan(
                # define to which task to connect this function
                task,
                # use this analogue input channel
                self._analogue_input_channels[analogue_channel],
                # name to assign to it
                "Analogue Voltage Reader {}".format(analogue_channel),
                # the analogue input read mode (rse, nres or diff)
                # daq.DAQmx_Val_Diff,
                daq.DAQmx_Val_RSE,
                # the minimum input voltage expected
                self._ai_voltage_range[analogue_channel][0],
                # the minimum input voltage expected
                self._ai_voltage_range[analogue_channel][1],  # Todo: check type
                # the units in which the voltage is to be measured is volt
                daq.DAQmx_Val_Volts,
                # must be None unless units is set to "DAQmx_Val_FromCustomScale"
                None)

            # Set timing to finite amount of sample:
            daq.DAQmxCfgSampClkTiming(
                # define to which task to connect this function
                task,
                # assign a named Terminal for the clock source
                my_clock_channel + 'InternalOutput',
                # The sampling rate in samples per second per channel. Set this value to the
                # maximum expected rate of that clock.
                clock_frequency,
                # the edge off the clock on which to acquire the sample
                daq.DAQmx_Val_Rising,
                # Sample Mode: set the task to read a specified number of samples
                daq.DAQmx_Val_FiniteSamps,
                # the specified number of samples to read
                samples)
            self._analogue_input_daq_tasks[analogue_channel] = task
            self._analogue_input_samples[analogue_channel] = samples
        except:
            self.log.exception('Error while setting up analogue voltage reader for channel'
                               '{}.'.format(analogue_channel))
            return -1
        return 0

    def add_analogue_reader_channel_to_measurement(self, analogue_channel_orig,
                                                   analogue_channels):
        """
        This function adds additional channels to an already existing analogue reader task.
        Thereby many channels can be measured, read and stopped simultaneously.
        For this method another method needed to setup a task already.
        Use e.g. set_up_analogue_voltage_reader_scanner

        @param string analogue_channel_orig: the representative name of the analogue channel
                                    task to which this channel is to be added
        @param List(string) analogue_channels: The new channels to be added to the task

        @return int: error code (0:OK, -1:error)
        """
        # Check if channel exists
        if analogue_channel_orig not in self._analogue_input_channels.keys():
            self.log.error("The given analogue input task channel %s to which the channel was to "
                           "be added did not exist.", analogue_channel_orig)
            return -1
        # check variable type
        if not isinstance(analogue_channels, (frozenset, list, set, tuple, np.ndarray,)):
            self.log.error('Channels are not given in array type.')
            return -1

        for channel in analogue_channels:
            if channel not in self._analogue_input_channels.keys():
                self.log.error("The given analogue input channel %s is not defined. Please define the "
                               "input channel", channel)
                return -1
            # check if no task for channel to be added is configured
            if channel in self._analogue_input_daq_tasks:
                self.log.error('The same channel %s already has an existing input task running, '
                               'close this one first.', channel)
                return -1

        # check if task to which channel is added exists
        if analogue_channel_orig in self._analogue_input_daq_tasks.keys():
            # if existing use this task
            task = self._analogue_input_daq_tasks[analogue_channel_orig]
        else:
            self.log.error("The given analogue input task channel %s to which the channel was to "
                           "be added did not exist yet. Create this one first.", analogue_channel_orig)
            return -1

        # check if clock is running in case clock is needed (samples >1)
        if analogue_channel_orig not in self._clock_daq_task_new and self._analogue_input_samples[
            analogue_channel_orig] != 1:
            self.log.error('No clock running, call set_up_clock before starting the analogue '
                           'reader.')
            return -1

        for channel in analogue_channels:
            try:  # Creates a channel to measure a voltage and adds it to task:
                daq.DAQmxCreateAIVoltageChan(
                    # define to which task to connect this function
                    task,
                    # use this analogue input channel
                    self._analogue_input_channels[channel],
                    # name to assign to it
                    "Analogue Voltage Reader {}".format(channel),
                    # the analogue input read mode (rse, nres or diff)
                    daq.DAQmx_Val_RSE,
                    # daq.DAQmx_Val_Diff,
                    # the minimum input voltage expected
                    self._ai_voltage_range[channel][0],
                    # the minimum input voltage expected
                    self._ai_voltage_range[channel][1],  # Todo: check type
                    # the units in which the voltage is to be measured is volt
                    daq.DAQmx_Val_Volts,
                    # must be None unless units is set to "DAQmx_Val_FromCustomScale"
                    None)
                # add an "additional" task to the task list for this channel so it can be checked if
                # channel is configured.
                self._analogue_input_daq_tasks[channel] = task
            except:
                self.log.exception('Error while setting up analogue voltage reader for channel'
                                   '{}.'.format(channel))
                return -1
            # add sample number for this channel
            self._analogue_input_samples[channel] = self._analogue_input_samples[analogue_channel_orig]
            if analogue_channel_orig in self._clock_daq_task_new:
                # add channels to clock task if this is a clocked task, but only if it doesn`t exist yet ( necessary for stepping )
                # Todo: This can be done better
                for channel in analogue_channels:
                    if channel not in self._clock_daq_task_new:
                        self.add_clock_task_to_channel(analogue_channel_orig, [channel])
        return 0

    def set_up_continuous_analog_reader(self, analogue_channel):
        """Initializes task for reading an analogue input voltage with the Nidaq continuously
        at a given frequency.

        It reads a RSE connected voltage from the analogue inputs. For every period of
        time (given by the frequency) it reads the voltage at the analogue channel.

        @param string analogue_channel: the representative name of the analogue channel for
                                        which the task is created

        @return int: error code (0:OK, -1:error)
        """
        if analogue_channel not in self._analogue_input_channels.keys():
            self.log.error("The given analogue input channel %s is not defined. Please define the "
                           "input channel", analogue_channel)
            return -1

        if analogue_channel not in self._clock_daq_task_new:
            self.log.error('No clock running, call set_up_clock before starting the analogue '
                           'reader.')
            return -1

        if analogue_channel in self._analogue_input_daq_tasks:
            self.log.error('An analogue input task for this channel is already running, '
                           'close this one first.')
            return -1

        if analogue_channel not in self._clock_channel_new:
            self.log.error("The clock channel for this task %s is not defined.", analogue_channel)
            return -1
        my_clock_channel = self._clock_channel_new[analogue_channel]

        if analogue_channel not in self._clock_frequency_new:
            self.log.error("The clock frequency for this task %s is not defined.", analogue_channel)
            return -1
        # Todo: Fins usage of analaogue clock frequency.
        clock_frequency = self._clock_frequency_new[analogue_channel]

        try:
            # for i, ch in enumerate(my_counter_channels):
            task = daq.TaskHandle()
            daq.DAQmxCreateTask('Analogue Input {}'.format(analogue_channel), daq.byref(task))

            # Creates a channel to measure a voltage and adds it to task:
            daq.DAQmxCreateAIVoltageChan(
                # define to which task to connect this function
                task,
                # use this analogue input channel
                self._analogue_input_channels[analogue_channel],
                # name to assign to it
                "Analogue Voltage Reader {}".format(analogue_channel),
                # the analogue input read mode (rse, nres or diff)
                daq.DAQmx_Val_RSE,
                # the minimum input voltage expected
                self._ai_voltage_range[analogue_channel][0],
                # the minimum input voltage expected
                self._ai_voltage_range[analogue_channel][1],
                # the units in which the voltage is to be measured is volt
                daq.DAQmx_Val_Volts,
                # must be None unless units is set to "DAQmx_Val_FromCustomScale"
                None)

            # Set timing:
            daq.DAQmxCfgSampClkTiming(
                # define to which task to connect this function
                task,
                # assign a named Terminal for the clock source
                my_clock_channel + 'InternalOutput',
                # The sampling rate in samples per second per channel. Set this value to the
                # maximum expected rate of that clock.
                clock_frequency,
                # the edge off the clock on which to acquire the sample
                daq.DAQmx_Val_Rising,
                # Sample Mode: set the task to read a specified number of samples
                daq.DAQmx_Val_ContSamps,
                # the buffer size of the system
                1000)

            # Specifies the point in the buffer at which to begin a read operation.
            daq.DAQmxSetReadRelativeTo(
                # define to which task to connect this function
                task,
                # Start reading samples relative to the last sample returned by the previous read
                daq.DAQmx_Val_CurrReadPos)

            # Set the Read Offset.
            # Specifies an offset in samples per channel at which to begin a read
            # operation. This offset is relative to the location you specify with
            # RelativeTo. Here we set the Offset to 0 for multiple samples:
            daq.DAQmxSetReadOffset(task, 0)

            # Set Read OverWrite Mode.
            # Specifies whether to overwrite samples in the buffer that you have
            # not yet read. Here operation will bes stopped if buffer gets to large
            daq.DAQmxSetReadOverWrite(
                task,
                daq.DAQmx_Val_DoNotOverwriteUnreadSamps)

            self._analogue_input_daq_tasks[analogue_channel] = task
            self._analogue_input_samples[analogue_channel] = None

        except:
            self.log.exception('Error while setting up analogue voltage reader for channel'
                               '{}.'.format(analogue_channel))
            return -1
        return 0

    # Todo: Add option to keep track of the result per channel as with a dictionary it might change for every channel
    # but it is defined in  a very specific way.
    def set_up_analogue_voltage_reader_clock(self, analogue_channel, clock_frequency=None, clock_channel=None,
                                             set_up=True):
        """ Configures the hardware clock of the NiDAQ card to give the timing.
        @param key analogue_channel: The channel for which the clock is to be setup

        @param float clock_frequency: if defined, this sets the frequency of
                                      the clock (in Hz)
        @param string clock_channel: if defined, this is the physical channel
                                     of the clock
        @param bool set_up: If True, the function does nothing and assumes clock is already set up from different task
                                    using the same clock

        @return int: error code (0:OK, -1:error)
        """
        # The clock for the analogue clock is created on the same principle as it is
        # for the counter. Just to keep consistency, this function is a wrapper
        # around the set_up_clock. However if a clock might already be configured for a different
        # task, this might not be a problem for the programmer, so he can call the function
        # anyway but set set_up to False and the function does nothing.
        if not set_up:
            # this exists, so that one can "set up" the clock that is used in parallel in the
            # code but not in reality and serves readability in the logic code
            return 0

        # Todo: Check if this divided by 2 is sensible  # because it will be multiplied by 2 in the setup
        return self.set_up_clock_new(analogue_channel,
                                     clock_frequency=clock_frequency,
                                     clock_channel=clock_channel)

    def start_analogue_voltage_reader(self, analogue_channel, start_clock=False):
        """
        Starts the preconfigured analogue input task

        @param  string analogue_channel: the representative name of the analogue channel for
                                        which the task is created
        @param  bool start_clock: default value false, bool that defines if clock for the task is
                                also started.

        @return int: error code (0:OK, -1:error)
        """
        if self._analogue_input_started:
            return 0

        if type(analogue_channel) != str:
            self.log.error("analogue channel needs to be passed as a string. A different "
                           "variable type (%s) was used", type(analogue_channel))
            return -1

        if analogue_channel in self._analogue_input_daq_tasks:
            if start_clock:
                try:  # Stop clock
                    daq.DAQmxStopTask(self._clock_daq_task_new[analogue_channel])
                except:
                    self.log.warning('Error while stopping analogue voltage reader clock')
                try:  # star
                    daq.DAQmxStartTask(self._clock_daq_task_new[analogue_channel])
                except:
                    self.log.error('Error while starting up analogue voltage reader clock')
                    return -1
            try:
                daq.DAQmxStartTask(self._analogue_input_daq_tasks[analogue_channel])
            except:
                self.log.exception('Error while starting up analogue voltage reader.')
                return -1
            self._analogue_input_started = True
            return 0

        else:
            self.log.error(
                'Cannot start analogue voltage reader since it is not configured!\n'
                'Run the set_up_analogue_voltage_reader or set_up_analogue_voltage_reader_scanner routine first.')
            return -1

    def get_analogue_voltage_reader(self, analogue_channels, read_samples=None):
        """"
        Returns the last voltages read by the analog input reader

        @param  List(string) analogue_channels: the representative name of the analogue channels
                                        for which channels are read.
                                        The first list element must be the one for which the
                                        task was created
        @param int read_samples: The amount of samples to be read from the buffer for a continuous mode acquisition. Not
                                        needed for finite amount of samples

        @return np.array, int: The input voltage (array) and the amount of samples read (int). For
                                error array with length 2 and entry -1, 0
        """
        # check variable type
        if not isinstance(analogue_channels, (frozenset, list, set, tuple, np.ndarray,)):
            self.log.error('Channels are not given in array type.')
            return np.array([-1.]), 0

        # test if the analogue channel is configured for all channels given
        error = False
        if analogue_channels[0] in self._analogue_input_samples.keys() and read_samples is None:
            samples = self._analogue_input_samples[analogue_channels[0]]
        elif read_samples is None:
            self.log.error("The given channel %s is not properly defined", analogue_channels[0])
            return np.array([-1.]), 0
        else:
            samples = read_samples

        for channel in analogue_channels:
            if channel not in self._analogue_input_channels.keys():
                error = True
                self.log.error(
                    "The given channel %s is not part of the possible channels. Configure this channel first", channel)
            elif channel not in self._analogue_input_daq_tasks.keys():
                error = True
                self.log.error("No task was specified for the given channel %s. Add this channel first to the analogue"
                               " reader task", channel)
            elif channel in self._analogue_input_samples:
                if samples != self._analogue_input_samples[channel]:
                    self.log.error(
                        "The channel %s is does not have the same number of samples as channel %s. "
                        "They can not be part of the same task!", analogue_channels[0], channel)
                    error = True

        if error: return np.array([-1.]), 0

        if samples > 1:
            if analogue_channels[0] not in self._clock_daq_task_new:
                self.log.error(
                    "No clock task specified for this analogue reader. If more then one sample is acquired (%s) "
                    "a clock needs to be implemented.", samples)

        # Fixme: this timeout might really hurt for cavity stabilisation. make optional
        # *1.1 to have an extra (10%) short waiting time.
        if samples != 1:
            timeout = (samples * 1.1) / self._clock_frequency_new[analogue_channels[0]]
        else:
            timeout = -1
        # Count data will be written here
        _analogue_count_data = np.zeros(samples * len(analogue_channels), dtype=np.float64)
        # Number of samples which were read will be stored here
        n_read_samples = daq.int32()
        task = self._analogue_input_daq_tasks[analogue_channels[0]]
        try:
            daq.DAQmxReadAnalogF64(
                # read from this task
                task,
                # wait till all finite counts are acquired then return
                -1,
                # maximal timeout for the read process
                timeout,
                # defines that first all samples from one channel are returned and then
                # all from the next and so on
                daq.DAQmx_Val_GroupByChannel,
                # write into this array
                _analogue_count_data,
                # length of array to write into
                samples * len(analogue_channels),
                # number of samples which were actually read.
                daq.byref(n_read_samples),
                # Reserved for future use. Pass NULL (here None) to this parameter
                None)
        except:
            self.log.error('Error while reading the analogue voltages from NIDAQ')
            return np.array([-1.]), 0
        return _analogue_count_data, n_read_samples.value

    def stop_analogue_voltage_reader(self, analogue_channel):
        """"
        Stops the analogue voltage input reader task

        @analogue_channel str: one of the analogue channels for which the task to be stopped is
                            configured. If more than one channel uses this task,
                            all channel readings will be stopped.
        @return int: error code (0:OK, -1:error)
        """
        # check if correct type was specified
        if type(analogue_channel) != str:
            self.log.error("Analogue channel needs to be passed as a string. A different "
                           "variable type (%s) was used", type(analogue_channel))
            return -1
        # check if task for channel exists
        if analogue_channel in self._analogue_input_daq_tasks.keys():
            task = self._analogue_input_daq_tasks[analogue_channel]
            # try to stop task
            try:
                daq.DAQmxStopTask(task)
            except:
                self.log.exception('Error while stopping analogue reader for channel {'
                                   '}.'.format(analogue_channel))
                return -1
            self._analogue_input_started = False
            return 0

        else:
            self.log.error(
                'Cannot stop Analogue Input Reader Task since it is not running or configured!\n'
                'Start the Analogue Input Reader Task before you can actually stop it!')
            return -1

    def close_analogue_voltage_reader(self, analogue_channel):
        """"
        Closes the analogue voltage input reader and clears up afterwards

        @analogue_channel str: one of the analogue channels for which the task to be closed is
                            configured. If more than one channel uses this task,
                            all channel readings will be closed.
        @return int: error code (0:OK, -1:error)
        """
        # check if correct type was specified
        if type(analogue_channel) != str:
            self.log.error("Analogue channel needs to be passed as a string. A different "
                           "variable type (%s) was used", type(analogue_channel))
            return -1

        # check if task for channel exists
        if analogue_channel in self._analogue_input_daq_tasks:
            # retrieve task from dictionary and erase from dictionary
            task = self._analogue_input_daq_tasks.pop(analogue_channel)
            self._analogue_input_samples.pop(analogue_channel, None)

            # removes channels from task list that used the same task
            key_list = []
            for task_key, value in self._analogue_input_daq_tasks.items():
                if value == task:
                    key_list.append(task_key)
            for item in key_list:
                self._analogue_input_daq_tasks.pop(item)
                self._analogue_input_samples.pop(item)

            try:
                # stop the counter task
                daq.DAQmxStopTask(task)
                # after stopping delete all the configuration of the counter
                daq.DAQmxClearTask(task)
            except:
                self.log.exception('Could not close analogue input reader.')
                # re append task as closing did not work
                self._analogue_input_daq_tasks[analogue_channel] = task
                for key in key_list:
                    self._analogue_input_daq_tasks[key] = task
                return -1
            self._analogue_input_started = False
            return 0
        else:
            self.log.error(
                'Cannot close Analogue Input Reader Task since it is not running or configured!')
            return -1

    def close_analogue_voltage_reader_clock(self, analogue_channel, close=True):
        """ Closes the analogue voltage input reader clock and cleans up afterwards.
        @param key analogue_channel: The channel for which the clock is to be closed.
        @param bool close: decides if the clock is actually closed. If True closes and cleans up clock,
            else dummy method for logic

        @return int: error code (0:OK, -1:error)
        """
        if close:
            return self.close_clock_new(analogue_channel)
        else:
            # this way it is a dummy method to make programming from logic more consistent
            return 0

    # =============================== End AnalogReaderInterface Commands  =======================

    # =============================== Start AnalogOutputInterface Commands  =======================

    def set_up_analogue_output(self, analogue_channels=None, scanner=False):
        """ Starts or restarts the analog output.

        @param List(string) analogue_channels: the representative names  of the analogue channel for
                                        which the task is created in a list

        @param Bool scanner: Defines if a scanner analogue output is to be setup of if single
                                    channels are to be configured

        @return int: error code (0:OK, -1:error)
        """
        try:
            # If an analog task is already running, kill that one first
            if scanner:
                if self._scanner_ao_task is not None:
                    # stop the analog output task
                    daq.DAQmxStopTask(self._scanner_ao_task)

                    # delete the configuration of the analog output
                    daq.DAQmxClearTask(self._scanner_ao_task)

                    # set the task handle to None as a safety
                    self._scanner_ao_task = None

                # initialize ao channels / task for scanner, should always be active.
                # Define at first the type of the variable as a Task:
                self._scanner_ao_task = daq.TaskHandle()

                # create the actual analog output task on the hardware device. Via
                # byref you pass the pointer of the object to the TaskCreation function:
                daq.DAQmxCreateTask('ScannerAO', daq.byref(self._scanner_ao_task))
                for n, chan in enumerate(self._scanner_ao_channels):
                    # Assign and configure the created task to an analog output voltage channel.
                    daq.DAQmxCreateAOVoltageChan(
                        # The AO voltage operation function is assigned to this task.
                        self._scanner_ao_task,
                        # use (all) scanner ao_channels for the output
                        chan,
                        # assign a name for that channel
                        'Scanner AO Channel {0}'.format(n),
                        # minimum possible voltage
                        self._voltage_range[n][0],
                        # maximum possible voltage
                        self._voltage_range[n][1],
                        # units is Volt
                        daq.DAQmx_Val_Volts,
                        # scale for channel, if unit is custom. Therefore here its Null (None)
                        None)
            else:
                if analogue_channels is None:
                    self.log.error("If you do not initialise a scanner "
                                   "you need to pass the analogue channels to be initialised.")
                else:
                    # check if channels exist:
                    for channel in analogue_channels:
                        if channel not in self._analogue_output_channels.keys():
                            self.log.error("The given analogue output channel %s is not defined. Please define the "
                                           "output channel", channel)
                            return -1
                        # check if no task for channel to be added is configured
                        if channel in self._analogue_output_daq_tasks.keys():
                            self.log.error('The same analogue output channel %s already has '
                                           'an existing output task running, close this one first.', channel)
                            return -1
                        # Todo: This needs to have check if the channel is already used in the scanner.
                        # However this is not possible in a sensible way right now, because the scanner channels are
                        # passed as a full list and not a dictionary and it is not possible to find out which two/three
                        # of the 3/4 possible options are used at the moment.
                        # elif channel in ["x", "y", "z"]:
                        #    self.log.error('The same channel %s already has an existing output task running, '
                        #                   'close this one first.',channel)
                        #    return -1

                    # create the actual analog output task on the hardware device. Via
                    # byref you pass the pointer of the object to the TaskCreation function:
                    task = daq.TaskHandle()
                    # the analogue output get the name of the first channel
                    daq.DAQmxCreateTask('Analogue Output {}'.format(analogue_channels[0]), daq.byref(task))

                    for chan in analogue_channels:
                        # Assign and configure the created task to an analog output voltage channel.
                        daq.DAQmxCreateAOVoltageChan(
                            # The AO voltage operation function is assigned to this task.
                            task,
                            # channel to use for output
                            self._analogue_output_channels[chan],
                            # assign a name for that channel
                            'AO Channel ' + chan,
                            # minimum possible voltage
                            self._ao_voltage_range[chan][0],
                            # maximum possible voltage
                            self._ao_voltage_range[chan][1],
                            # units is Volt
                            daq.DAQmx_Val_Volts,
                            # scale for channel, if unit is custom. Therefore here its Null (None)
                            None)
                        self._analogue_output_daq_tasks[chan] = task
                # daq.DAQmxSetSampTimingType(self._analogue_output_channels[self._analogue_output_daq_tasks[
                #    analogue_channels[0]]], daq.DAQmx_Val_OnDemand)
        except:
            self.log.exception('Error starting analog output task.')
            return -1
        return 0

    def write_ao(self, analogue_channel, voltages, length=1, start=False, time_out=0):
        """Writes a set of voltages to the analog outputs.

        @param  string analogue_channel: the representative name of the analogue channel for
                                        which the voltages are written

        @param List[float] voltages: array of n-part tuples defining the voltages to be generated

        @param int length: number of samples to be generated per analogue  channel (each channel must have the same
                                amount of samples)

        @param bool start: write immediately (True) or wait for start of task (False)

        @param float time_out: default 0, value how long the program should maximally take two write the samples
                                0 returns an error if program fails to write immediately.

        @return int: how many values were actually written
        """

        # check if task for channel is configured
        if analogue_channel not in self._analogue_output_daq_tasks:
            self.log.error('The analogue output channel %s has no output task configured.', analogue_channel)
            return -1
        # Number of samples which were actually written, will be stored here.
        # The error code of this variable can be asked with .value to check
        # whether all channels have been written successfully.
        samples_written = daq.int32()
        # write the voltage instructions for the analog output to the hardware
        daq.DAQmxWriteAnalogF64(
            # write to this task
            self._analogue_output_daq_tasks[analogue_channel],
            # length of the command (points)
            length,
            # start task immediately (True), or wait for software start (False)
            start,
            # maximal timeout in seconds for the write process
            time_out,
            # Specify how the samples are arranged: each pixel is grouped by channel number
            daq.DAQmx_Val_GroupByChannel,
            # the voltages to be written
            voltages,
            # The actual number of samples per channel successfully written to the buffer
            daq.byref(samples_written),
            # Reserved for future use. Pass NULL(here None) to this parameter
            None)
        return samples_written.value

    def set_up_analogue_output_clock(self, analogue_channel, clock_frequency=None, clock_channel=None,
                                     set_up=True):
        """ Configures the hardware clock of the NiDAQ card to give the timing.

        @param key analogue_channel: The channel for which the clock is to be setup
        @param float clock_frequency: if defined, this sets the frequency of
                                      the clock (in Hz). If not defined the scanner clock frequency will be used.
        @param string clock_channel: if defined, this is the physical channel
                                     of the clock
        @param bool set_up: If True, the function does nothing and assumes clock is already set up from different task
                                    using the same clock

        @return int: error code (0:OK, -1:error)
        """
        # The clock for the analogue clock is created on the same principle as it is
        # for the counter. Just to keep consistency, this function is a wrapper
        # around the set_up_clock. However if a clock might already be configured for a different
        # task, this might not be a problem for the programmer, so he can call the function
        # anyway but set set_up to False and the function does nothing.
        if not set_up:
            # this exists, so that one can "set up" the clock that is used in parallel in the
            # code but not in reality and serves readability in the logic code
            return 0

        return self.set_up_clock_new(analogue_channel,
                                     clock_frequency=clock_frequency,  # because it will be multiplied by 2 in the setup
                                     clock_channel=clock_channel)

    def configure_analogue_timing(self, analogue_channel, length):
        """
        Set the timing of this analogue channel to a finite amount of samples (length) with implicit timing
        @param key analogue_channel: The channel for which the timing is to be configured
        @param int length: The amount of clock cycles to be set

        @return int: error code (0:OK, -1:error)
        """

        if analogue_channel not in self._analogue_output_daq_tasks:
            self.log.error('The analogue output channel %s has no output task configured.', analogue_channel)
            return -1
        if analogue_channel not in self._clock_daq_task_new:
            self.log.error('The analogue output channel %s has no clock task configured.', analogue_channel)
            return -1
        if not isinstance(length, int):
            self.log.error("The amount of samples needs to be given as integer, but type %s was given.", type(length))

        try:
            daq.DAQmxCfgSampClkTiming(
                # add to this task
                self._analogue_output_daq_tasks[analogue_channel],
                # use this channel as clock
                self._clock_channel_new[analogue_channel] + 'InternalOutput',
                # Maximum expected clock frequency
                self._clock_frequency_new[analogue_channel],
                # Generate sample on falling edge
                daq.DAQmx_Val_Falling,
                # generate finite number of samples
                daq.DAQmx_Val_FiniteSamps,
                # number of samples to generate
                length)

            daq.DAQmxCfgImplicitTiming(
                # define task
                self._clock_daq_task_new[analogue_channel],
                # only a limited number of# counts
                daq.DAQmx_Val_FiniteSamps,
                # count twice for each voltage +1 for safety
                length)
        except:
            self.log.exception("Not possible to configure timing for analogue channel %s", analogue_channel)
            return -1
        return 0

    def analogue_scan_line_positions(self, analogue_channels, positions):
        """Scans a line of positions for the given channels

        @param list[str] analogue_channels: the channels for which the voltages should be written
        @param array[][][] positions: the positions to be moved by the NIDAQ

        @return np.array: the positions written. If an error occured returns  [-1]
        """
        if analogue_channels.any() not in self._analogue_output_daq_tasks:
            self.log.error('The analogue output channel %s has no output task configured.', analogue_channels)
            return -1

        if not isinstance(positions, (frozenset, list, set, tuple, np.ndarray,)):
            self.log.error('Given position list is no array type.')
            return [-1]

        if not set(analogue_channels).issubset(self._a_o_pos_ranges):
            self.log.error("for one of the given analogue channels (%s) there is not position range defined",
                           analogue_channels)
            return [-1]

        if not set(analogue_channels).issubset(self._a_o_ranges):
            self.log.error("for one of the given analogue channels (%s) there is not voltage range defined",
                           analogue_channels)
            return [-1]

        voltage_array = np.zeros(np.shape(positions))
        i = 0
        for channel in analogue_channels:
            v_range = self._a_o_ranges[channel]
            pos_range = self._a_o_pos_ranges[channel]
            voltage_array[:,:,i] = (v_range[1] - v_range[0]) / (pos_range[1] - pos_range[0]) * (
                        positions[:, :, i] - v_range[0]) +v_range[0]
            if np.min(voltage_array[i]) < v_range[0] or np.max(voltage_array[i]) > v_range[1]:
                self.log.error(
                    'Voltages (%s, %s) exceed the limit, the positions have to '
                    'be adjusted to stay in the given range.',np.min(voltage_array[i]),np.max(voltage_array[i]))
                return [-1]

        self.analogue_scan_line(analogue_channels[0], voltage_array)

        return positions

    def analogue_scan_line(self, analogue_channel, voltages):
        """Scans a line of voltages for the task of the given channel

        @param analogue_channel: the channels for which the voltages should be written
        @param voltages: the positions to be written

        @return np.array: the voltages written. If an error occured returns  -1
        """
        # check if task for channel is configured
        if analogue_channel not in self._analogue_output_daq_tasks:
            self.log.error('The analogue output channel %s has no output task configured.', analogue_channel)
            return -1

        voltages_array = np.array(voltages)
        # length: number of samples per scanned channel
        length = voltages_array.shape[-1]  # gives the length of the innermost array and works also for a 1D array

        if analogue_channel not in self._clock_daq_task_new:
            self.log.error('The analogue output channel %s has no clock task configured.', analogue_channel)
            return -1

        try:
            # write the positions to the analog output
            written_voltages = self.write_ao(analogue_channel,
                                             voltages=voltages_array,  # .flatten()?
                                             length=length,
                                             start=False, time_out=self._RWTimeout)

            # start the timed analog output task
            self.start_analogue_output(analogue_channel)

            daq.DAQmxStopTask(self._clock_daq_task_new[analogue_channel])
            daq.DAQmxStartTask(self._clock_daq_task_new[analogue_channel])
            time_out = 1. / self._clock_frequency_new[analogue_channel]
            # wait for the scanner clock to finish
            daq.DAQmxWaitUntilTaskDone(
                # define task
                self._clock_daq_task_new[analogue_channel],
                # maximal timeout for the counter times the positions
                time_out * 2 * length)
            # output = self.get_analogue_voltage_reader(["APD"])
            # stop the clock task
            daq.DAQmxStopTask(self._clock_daq_task_new[analogue_channel])

            # stop the analog output task
            self.stop_analogue_output(analogue_channel)

        except:
            self.log.exception('Error while scanning  voltage output line.')
            return -1
        return written_voltages

    def start_analogue_output(self, analogue_channel, start_clock=False):
        """
        Starts the preconfigured analogue out task

        @param  string analogue_channel: the representative name of the analogue channel for
                                        which the task is created
        @param  bool start_clock: default value false, bool that defines if clock for the task is
                                also started.

        @return int: error code (0:OK, -1:error)
        """
        if type(analogue_channel) != str:
            self.log.error("analogue channel needs to be passed as a string. A different "
                           "variable type (%s) was used", type(analogue_channel))
            return -1
        if analogue_channel in self._analogue_output_daq_tasks:
            if start_clock:
                try:  # Stop clock
                    daq.DAQmxStopTask(self._clock_daq_task_new[analogue_channel])
                except:
                    self.log.warning('Error while stopping analogue voltage reader clock')
                try:  # star
                    daq.DAQmxStartTask(self._clock_daq_task_new[analogue_channel])
                except:
                    self.log.error('Error while starting up analogue voltage reader clock')
                    return -1
            try:
                daq.DAQmxStartTask(self._analogue_output_daq_tasks[analogue_channel])
            except:
                self.log.exception('Error while starting up analogue voltage reader.')
                return -1
            return 0

        else:
            self.log.error(
                'Cannot start analogue voltage reader for channel %s since it is not configured!\n'
                'Run the set_up_analogue_voltage_reader or set_up_analogue_voltage_reader_scanner routine first.',
                analogue_channel)
            return -1

    def stop_analogue_output(self, analogue_channel):
        """"
        Stops the analogue voltage output task

        @analogue_channel str: one of the analogue channels for which the task to be stopped is
                            configured. If more than one channel uses this task,
                            all channel readings will be stopped.
        @return int: error code (0:OK, -1:error)
        """
        # check if correct type was specified
        if type(analogue_channel) != str:
            self.log.error("analogue channel needs to be passed as a string. A different "
                           "variable type (%s) was used", type(analogue_channel))
            return -1
        # check if task for channel exists
        if analogue_channel in self._analogue_output_daq_tasks.keys():
            task = self._analogue_output_daq_tasks[analogue_channel]
            # try to stop task
            try:
                daq.DAQmxStopTask(task)
            except:
                self.log.exception('Error while stopping analogue output for channel {%s}.', analogue_channel)
                return -1
            return 0

        else:
            self.log.error(
                'Cannot stop Analogue Output Task for channel %s since it is not running or configured!\n'
                'Start the Analogue Output Task before you can actually stop it!', analogue_channel)
            return -1

    def close_analogue_output(self, analogue_channel=None, scanner=False):
        """ Stops the analog output task.

        @param key analogue_channel: one of the analogue channels for which the task to be stopped is
                            configured. If more than one channel uses this task,
                            all channel readings will be stopped.

        @param Bool scanner: Defines if a scanner analogue output is to be setup of if single
                                channels are to be configured

        @return int: error code (0:OK, -1:error)
        """
        if scanner:
            retval = 0
            if self._scanner_ao_task is None:
                return -1

            try:
                # stop the analog output task
                daq.DAQmxStopTask(self._scanner_ao_task)
            except:
                self.log.exception('Error stopping analog output.')
                retval = -1
            try:
                daq.DAQmxClearTask(self._scanner_ao_task)
            except:
                self.log.exception('Error closing analog output mode.')
                retval = -1
            return retval

        else:
            # check if correct type was specified
            if type(analogue_channel) != str:
                self.log.error("Analogue channel needs to be passed as a string. A different "
                               "variable type (%s) was used", type(analogue_channel))
                return -1
            # check if task for channel exists
            if analogue_channel in self._analogue_output_daq_tasks.keys():
                # retrieve task from dictionary and erase from dictionary
                task = self._analogue_output_daq_tasks.pop(analogue_channel)

                # removes channels from task list that used the same task
                key_list = []
                for task_key, value in self._analogue_output_daq_tasks.items():
                    if value == task:
                        key_list.append(task_key)
                for item in key_list:
                    self._analogue_output_daq_tasks.pop(item)

                try:
                    # stop the counter task
                    daq.DAQmxStopTask(task)
                    # after stopping delete all the configuration of the counter
                    daq.DAQmxClearTask(task)
                except:
                    self.log.exception('Could not close analogue output reader.')
                    # re append task as closing did not work
                    self._analogue_output_daq_tasks[analogue_channel] = task
                    for key in key_list:
                        self._analogue_output_daq_tasks[key] = task
                    return -1
                return 0
            else:
                self.log.error(
                    'Cannot close Analogue Input Reader Task since it is not running or configured!')
                return -1

    def close_analogue_output_clock(self, analogue_channel, close=True):
        """ Closes the analogue output clock and cleans up afterwards.

        @param key analogue_channel: The channel for which the clock is to be closed.
        @param bool close: decides if the clock is actually closed. If True closes and cleans up clock,
            else dummy method for logic

        @return int: error code (0:OK, -1:error)
        """
        if close:
            return self.close_clock_new(analogue_channel)
        else:
            # this way it is a dummy method to make programming from logic more consistent
            return 0

    # =============================== End AnalogOutputInterface Commands  =======================

    # =============================== Start Clock Commands  =======================

    def set_up_clock_new(self, name, clock_frequency=None, clock_channel=None, idle=False, start=False):
        """ Configures the hardware clock of the NiDAQ card to give the timing.

        @param key name: the pointer for the configured task

        @param float clock_frequency: if defined, this sets the frequency of
                                      the clock in Hz
        @param string clock_channel: if defined, this is the physical channel
                                     of the clock within the NI card.
        @param bool idle: set whether idle situation of the counter (where
                          counter is doing nothing) is defined as
                                True  = 'Voltage High/Rising Edge'
                                False = 'Voltage Low/Falling Edge'
        @param bool start: sets whether clock is started right away

        @return int: error code (0:OK, -1:error)
        """

        if name in self._clock_daq_task_new:
            self.log.error('A clock task for this axis is already running, close this one first.')
            return -1

        # assign the clock frequency, if given
        if clock_frequency is None or clock_frequency <= 0.0 or not isinstance(clock_frequency, (int, float)):
            self._clock_frequency_new[name] = float(self._dummy_frequency)
            self.log.info("no clock frequency given, using dummy frequency (%s Hz)instead.", self._dummy_frequency)
        else:
            self._clock_frequency_new[name] = float(clock_frequency)

        # use the correct clock in this method
        my_clock_frequency = self._clock_frequency_new[name]

        # assign the clock channel, if given
        if clock_channel is not None:
            my_clock_channel = clock_channel
        else:
            for i in self._clock_channels:
                if i not in self._clock_channel_new.values():
                    my_clock_channel = i
                    break
            else:
                self.log.error(
                    "There is no clock channel free to be used for this task. Stop another clock channel first to"
                    " free the necessary resources.")
                return -1

        if my_clock_channel in self._clock_channel_new.values():
            self.log.warn("This clock channel (%s) is already being used. This might lead to clashes. "
                          "Therefore method ist stopped", my_clock_channel)
            return -1
        # Fixme: The line above tries to mimic the old lines below.
        # check whether only one clock pair is available, since some NI cards
        # only one clock channel pair.
        # if self._scanner_clock_channel == self._clock_channel:
        #    if not ((self._clock_daq_task is None) and (self._scanner_clock_daq_task is None)):
        #        self.log.error(
        #            'Only one clock channel is available!\n'
        #            'Another clock is already running, close this one first '
        #            'in order to use it for your purpose!')
        #        return -1

        self._clock_channel_new[name] = my_clock_channel
        # Adjust the idle state if necessary
        my_idle = daq.DAQmx_Val_High if idle else daq.DAQmx_Val_Low
        try:
            # Create handle for task
            my_clock_daq_task = daq.TaskHandle()

            # create task for clock
            task_name = str(name)
            daq.DAQmxCreateTask(task_name, daq.byref(my_clock_daq_task))

            # create a digital clock channel with specific clock frequency:
            daq.DAQmxCreateCOPulseChanFreq(
                # The task to which to add the channels
                my_clock_daq_task,
                # which channel is used?
                my_clock_channel,
                # Name to assign to task (NIDAQ uses by # default the physical channel name as
                # the virtual channel name. If name is specified, then you must use the name
                # when you refer to that channel in other NIDAQ functions)
                'Clock Producer ' + task_name,
                # units, Hertz in our case
                daq.DAQmx_Val_Hz,
                # idle state
                my_idle,
                # initial delay
                0,
                # pulse frequency
                my_clock_frequency,
                # duty cycle of pulses, 0.5 such that high and low duration are both
                # equal to count_interval
                0.5)

            # Configure Implicit Timing.
            # Set timing to continuous, i.e. set only the number of samples to
            # acquire or generate without specifying timing:
            daq.DAQmxCfgImplicitTiming(
                # Define task
                my_clock_daq_task,
                # Sample Mode: set the task to generate a continuous amount of running samples
                daq.DAQmx_Val_ContSamps,
                # buffer length which stores temporarily the number of generated samples
                1000)

            self._clock_daq_task_new[name] = my_clock_daq_task
            if start:
                # actually start the preconfigured clock task
                daq.DAQmxStartTask(my_clock_daq_task)
        except:
            self.log.exception('Error while setting up clock %s.', name)
            return -1
        return 0

    def add_clock_task_to_channel(self, channel_name_orig, channel_names):
        """
        This function adds additional pointer to an already existing clock task.
        Thereby many pointers can control this task.
        this is helpful if the same clock is used for different purposes or synchronisation.
        For this method another method needed to setup the clock task already.
        Use set_up_clock_new to make a new clock task

        @param key channel_name_orig: the representative name of the clock
                                    task to which this channel is to be added
        @param List(keys) channel_names: The new channels to be added to the task (eg. analogue output cavity scanner)

        @return int: error code (0:OK, -1:error)
        """
        if not (channel_names, (frozenset, list, set, tuple, np.ndarray,)):
            self.log.error('Channels are not given in array type.')
            return -1
        if channel_name_orig not in self._clock_daq_task_new:
            self.log.error("The given clock task pointer %s to which the channel was to "
                           "be added did not exist yet. Create this one first.", channel_name_orig)
            return -1
        my_task = self._clock_daq_task_new[channel_name_orig]
        my_channel = self._clock_channel_new[channel_name_orig]
        my_frequency = self._clock_frequency_new[channel_name_orig]

        for channel in channel_names:
            # check if no task for channel to be added is configured
            if channel in self._clock_daq_task_new:
                self.log.error('The same channel %s already has an existing clock task running, '
                               'close this one first.', channel)
                return -1
            self._clock_daq_task_new[channel] = my_task
            self._clock_channel_new[channel] = my_channel
            self._clock_frequency_new[channel] = my_frequency
        return 0

    def close_clock_new(self, name):
        """ Closes the clock and cleans up afterwards.

        @param key name: specifies the task name for which the clock is to be turned off


        @return int: error code (0:OK, -1:error)
        """

        if name in self._clock_daq_task_new:
            my_task = self._clock_daq_task_new.pop(name)
            my_channel = self._clock_channel_new.pop(name)
            my_frequency = self._clock_frequency_new.pop(name)
        else:
            self.log.error("There was no task specified for the clock (%s) that was tried to be closed.", name)
            return -1

        # removes channels from task list that used the same task
        key_list = []
        for task_key, value in self._clock_daq_task_new.items():
            if value == my_task:
                key_list.append(task_key)
        for item in key_list:
            self._clock_daq_task_new.pop(item)
            self._clock_channel_new.pop(item)
            self._clock_frequency_new.pop(item)

        try:
            # stop the clock task
            daq.DAQmxStopTask(my_task)
            # after stopping delete all the configuration of the counter
            daq.DAQmxClearTask(my_task)
        except:
            self.log.exception('Could not close clock %s.', name)
            self._clock_daq_task_new[name] = my_task
            for key in key_list:
                self._clock_daq_task_new[key] = my_task
                self._clock_channel_new[key] = my_channel
                self._clock_frequency_new[key] = my_frequency

            return -1
        return 0

    # =============================== End Clock Commands  =======================
