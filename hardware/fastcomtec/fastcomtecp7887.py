# -*- coding: utf-8 -*-

"""
This file contains the Qudi hardware file implementation for FastComtec p7887 .

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

#TODO: start stop works but pause does not work, i guess gui/logic problem
#TODO: What does get status do or need as return?
#TODO: Check if there are more modules which are missing, and more settings for FastComtec which need to be put, should we include voltage threshold?

from core.module import Base
from core.configoption import ConfigOption
from core.util.modules import get_main_dir
from interface.fast_counter_interface import FastCounterInterface
import time
import os
import numpy as np
import ctypes



"""
Remark to the usage of ctypes:
All Python types except integers (int), strings (str), and bytes (byte) objects
have to be wrapped in their corresponding ctypes type, so that they can be
converted to the required C data type.

ctypes type     C type                  Python type
----------------------------------------------------------------
c_bool          _Bool                   bool (1)
c_char          char                    1-character bytes object
c_wchar         wchar_t                 1-character string
c_byte          char                    int
c_ubyte         unsigned char           int
c_short         short                   int
c_ushort        unsigned short          int
c_int           int                     int
c_uint          unsigned int            int
c_long          long                    int
c_ulong         unsigned long           int
c_longlong      __int64 or
                long long               int
c_ulonglong     unsigned __int64 or
                unsigned long long      int
c_size_t        size_t                  int
c_ssize_t       ssize_t or
                Py_ssize_t              int
c_float         float                   float
c_double        double                  float
c_longdouble    long double             float
c_char_p        char *
                (NUL terminated)        bytes object or None
c_wchar_p       wchar_t *
                (NUL terminated)        string or None
c_void_p        void *                  int or None

"""
# Reconstruct the proper structure of the variables, which can be extracted
# from the header file 'struct.h'.

class AcqStatus(ctypes.Structure):
    """ Create a structured Data type with ctypes where the dll can write into.

    This object handles and retrieves the acquisition status data from the
    Fastcomtec.

    int started;                // acquisition status: 1 if running, 0 else
    double runtime;             // running time in seconds
    double totalsum;            // total events
    double roisum;              // events within ROI
    double roirate;             // acquired ROI-events per second
    double nettosum;            // ROI sum with background subtracted
    double sweeps;              // Number of sweeps
    double stevents;            // Start Events
    unsigned long maxval;       // Maximum value in spectrum
    """
    _fields_ = [('started', ctypes.c_int),
                ('runtime', ctypes.c_double),
                ('totalsum', ctypes.c_double),
                ('roisum', ctypes.c_double),
                ('roirate', ctypes.c_double),
                ('ofls', ctypes.c_double),
                ('sweeps', ctypes.c_double),
                ('stevents', ctypes.c_double),
                ('maxval', ctypes.c_ulong), ]

class AcqSettings(ctypes.Structure):
    """ Create a structured Data type with ctypes where the dll can write into.

    This object handles and retrieves the acquisition settings of the Fastcomtec.
    """

    _fields_ = [('range',       ctypes.c_ulong),
                ('prena',       ctypes.c_long),
                ('cftfak',      ctypes.c_long),
                ('roimin',      ctypes.c_ulong),
                ('roimax',      ctypes.c_ulong),
                ('eventpreset', ctypes.c_double),
                ('timepreset',  ctypes.c_double),
                ('savedata',    ctypes.c_long),
                ('fmt',         ctypes.c_long),
                ('autoinc',     ctypes.c_long),
                ('cycles',      ctypes.c_long),
                ('sweepmode',   ctypes.c_long),
                ('syncout',     ctypes.c_long),
                ('bitshift',    ctypes.c_long),
                ('digval',      ctypes.c_long),
                ('digio',       ctypes.c_long),
                ('dac0',        ctypes.c_long),
                ('dac1',        ctypes.c_long),
                ('swpreset',    ctypes.c_double),
                ('nregions',    ctypes.c_long),
                ('caluse',      ctypes.c_long),
                ('fstchan',     ctypes.c_double),
                ('active',      ctypes.c_long),
                ('calpoints',   ctypes.c_long), ]

class ACQDATA(ctypes.Structure):
    """ Create a structured Data type with ctypes where the dll can write into.

    This object handles and retrieves the acquisition data of the Fastcomtec.
    """
    _fields_ = [('s0', ctypes.POINTER(ctypes.c_ulong)),
                ('region', ctypes.POINTER(ctypes.c_ulong)),
                ('comment', ctypes.c_char_p),
                ('cnt', ctypes.POINTER(ctypes.c_double)),
                ('hs0', ctypes.c_int),
                ('hrg', ctypes.c_int),
                ('hcm', ctypes.c_int),
                ('hct', ctypes.c_int), ]


class FastComtec(Base, FastCounterInterface):
    """ Hardware Class for the FastComtec Card.

    unstable: Jochen Scheuer, Simon Schmitt

    Example config for copy-paste:

    fastcomtec_p7887:
        module.Class: 'fastcomtec.fastcomtecp7887.FastComtec'
        gated: False
        trigger_safety: 200e-9
        aom_delay: 400e-9
        minimal_binwidth: 0.25e-9

    """

    gated = ConfigOption('gated', False, missing='warn')
    trigger_safety = ConfigOption('trigger_safety', 200e-9, missing='warn')
    aom_delay = ConfigOption('aom_delay', 400e-9, missing='warn')
    minimal_binwidth = ConfigOption('minimal_binwidth', 0.25e-9, missing='warn')

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

        self.log.debug('The following configuration was found.')

        # checking for the right configuration
        if config:
            for key in config.keys():
                self.log.info('{0}: {1}'.format(key,config[key]))
        #this variable has to be added because there is no difference
        #in the fastcomtec it can be on "stopped" or "halt"
        self.stopped_or_halt = "stopped"
        self.timetrace_tmp = []

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        self.dll = ctypes.windll.LoadLibrary('dp7887.dll')
        #self.dll = ctypes.windll.LoadLibrary('p7887lib_no_server')
        if self.gated:
            self.change_sweep_mode(gated=True)
        else:
            self.change_sweep_mode(gated=False)
        return


    def on_deactivate(self):
        """ Deinitialisation performed during deactivation of the module.
        """
        return

    def get_constraints(self):
        """ Retrieve the hardware constrains from the Fast counting device.

        @return dict: dict with keys being the constraint names as string and
                      items are the definition for the constaints.

         The keys of the returned dictionary are the str name for the constraints
        (which are set in this method).

                    NO OTHER KEYS SHOULD BE INVENTED!

        If you are not sure about the meaning, look in other hardware files to
        get an impression. If still additional constraints are needed, then they
        have to be added to all files containing this interface.

        The items of the keys are again dictionaries which have the generic
        dictionary form:
            {'min': <value>,
             'max': <value>,
             'step': <value>,
             'unit': '<value>'}

        Only the key 'hardware_binwidth_list' differs, since they
        contain the list of possible binwidths.

        If the constraints cannot be set in the fast counting hardware then
        write just zero to each key of the generic dicts.
        Note that there is a difference between float input (0.0) and
        integer input (0), because some logic modules might rely on that
        distinction.

        ALL THE PRESENT KEYS OF THE CONSTRAINTS DICT MUST BE ASSIGNED!
        """

        constraints = dict()

        # the unit of those entries are seconds per bin. In order to get the
        # current binwidth in seconds use the get_binwidth method.
        constraints['hardware_binwidth_list'] = list(self.minimal_binwidth * (2 ** np.array(
                                                     np.linspace(0,24,25))))
        constraints['max_sweep_len'] = 6.8
        constraints['max_bins'] = 6.8/0.25e-9

        return constraints

    def configure(self, bin_width_s, record_length_s, number_of_gates=0, filename=None,
                  n_sequences=None, n_sweeps_preset=None):
        """ Configuration of the fast counter. Called from pulsedmeasurementlogic.

        @param float bin_width_s: Length of a single time bin in the time trace
                                  histogram in seconds.
        @param float record_length_s: Total length of the timetrace/each single
                                      gate in seconds.
        @param int number_of_gates: optional, number of gates in the pulse
                                    sequence. Ignore for not gated counter.
        @param int n_sequences: optional, number of data acquisitions of a whole 2d
                                array. Ignore for not gated counter.
        @param int n_sweeps_preset: optional, number of sweeps until card stops or moves to next cycle.
                                    Used in gate mode and more.

        @return tuple(binwidth_s, record_length_s, number_of_gates):
                    binwidth_s: float the actual set binwidth in seconds
                    gate_length_s: the actual record length in seconds
                    number_of_gates: the number of gated, which are accepted,
                    None if not-gated
        """

        # when not gated, record length = total sequence length, when gated, record length = laser length.
        # subtract 200 ns to make sure no sequence trigger is missed

        self.set_binwidth(bin_width_s)
        bin_width_new = self.get_binwidth()

        if self.gated:
            # add time to account for AOM delay
            no_of_bins = int((record_length_s + self.aom_delay) / bin_width_new)
        else:
            # subtract time to make sure no sequence trigger is missed
            no_of_bins = int((record_length_s - self.trigger_safety) / bin_width_new)

        self.set_length(no_of_bins)

        # cycles and sequences params
        if self.gated:
            self.set_cycles(number_of_gates)
            if n_sequences is not None:
                self.set_sequences(n_sequences)
            else:
                n_seq_max = 2**31-1     # approx. infinite repetitions by max int value
                n_sequences = n_seq_max
                self.set_sequences(n_sequences)

        # preset param, typically used in gate mode, but also differently
        if n_sweeps_preset is not None:
            self.set_preset(n_sweeps_preset)
        # don't set default value, since change_sweep_mode() might be called from script
        #else:
        #    if self.gated:
        #        self.set_preset(1)  # appropriate for most gated scenarios

        record_length = self.get_length() * bin_width_new

        if filename is not None:
            self._change_filename(filename)

        self.log.debug("Fastcomtec configuration written. "
                       "Record length: {}, binwidth: {}, gated: {}, cycles: {}, sweeps_preset: {}, sequences: {}".format(
                        record_length, bin_width_new, self.gated, number_of_gates if self.gated else 0, n_sweeps_preset,
                        n_sequences if self.gated else None))

        return self.get_binwidth(), record_length, number_of_gates



    def get_status(self):
        """
        Receives the current status of the Fast Counter and outputs it as return value.
        0 = unconfigured
        1 = idle
        2 = running
        3 = paused
        -1 = error state
        """
        status = AcqStatus()
        self.dll.GetStatusData(ctypes.byref(status), 0)
        # status.started = 3: hw is about to stop
        while status.started == 3:
            time.sleep(0.1)
            self.dll.GetStatusData(ctypes.byref(status), 0)

        if status.started == 1:
            return 2
        elif status.started == 0:
            if self.stopped_or_halt == "stopped":
                return 1
            elif self.stopped_or_halt == "halt":
                return 3
            else:
                self.log.error('There is an unknown status from FastComtec. The status message was %s' % (str(status.started)))
                return -1
        else:
            self.log.error(
                'There is an unknown status from FastComtec. The status message was %s' % (str(status.started)))
            return -1

    def get_current_runtime(self):
        """
        Returns the current runtime.
        @return float runtime: in s
        """
        status = AcqStatus()
        self.dll.GetStatusData(ctypes.byref(status), 0)
        return status.runtime

    def get_current_sweeps(self):
        """
        Returns the current sweeps.
        @return int sweeps: in sweeps
        """
        status = AcqStatus()
        self.dll.GetStatusData(ctypes.byref(status), 0)
        return status.sweeps

    def start_measure(self):
        """Start the measurement. """
        status = self.dll.Start(0)

        i_wait = 0
        n_wait_max = 20
        while self.get_status() != 2 and i_wait < n_wait_max:
            time.sleep(0.05)
            i_wait += 1

        if i_wait >= n_wait_max:
            self.log.warning("Starting fastcomtec timed out.")

        return status

    def stop_measure(self):
        """Stop the measurement. """
        self.stopped_or_halt = "stopped"
        status = self.dll.Halt(0)

        i_wait = 0
        n_wait_max = 20
        while self.get_status() != 1 and i_wait < n_wait_max:
            time.sleep(0.05)
            i_wait += 1

        if i_wait >= n_wait_max:
            self.log.warning("Stopping fastcomtec timed out.")

        if self.gated:
            self.timetrace_tmp = []
        return status

    def pause_measure(self):
        """Make a pause in the measurement, which can be continued. """
        self.stopped_or_halt = "halt"
        status = self.dll.Halt(0)
        while self.get_status() != 3:
            time.sleep(0.05)

        if self.gated:
            self.timetrace_tmp = self.get_data_trace()
        return status

    def continue_measure(self):
        """Continue a paused measurement. """
        if self.gated:
            status = self.start_measure()
        else:
            status = self.dll.Continue(0)
            while self.get_status() != 2:
                time.sleep(0.05)
        return status

    def is_gated(self):
        """ Check the gated counting possibility.

        @return bool: Boolean value indicates if the fast counter is a gated
                      counter (TRUE) or not (FALSE).
        """
        return self.gated

    def get_binwidth(self):
        """ Returns the width of a single timebin in the timetrace in seconds.

        @return float: current length of a single bin in seconds (seconds/bin)

        The red out bitshift will be converted to binwidth. The binwidth is
        defined as 2**bitshift*minimal_binwidth.
        """
        return self.minimal_binwidth*(2**int(self.get_bitshift()))

    def get_data_trace(self):
        """
        Polls the current timetrace data from the fast counter and returns it as a numpy array (dtype = int64).
        The binning specified by calling configure() must be taken care of in this hardware class.
        A possible overflow of the histogram bins must be caught here and taken care of.
        If the counter is UNgated it will return a 1D-numpy-array with returnarray[timebin_index]
        If the counter is gated it will return a 2D-numpy-array with returnarray[gate_index, timebin_index]

          @return arrray: Time trace.
        """
        setting = AcqSettings()
        self.dll.GetSettingData(ctypes.byref(setting), 0)
        N = setting.range

        if self.gated:
            bsetting=AcqSettings()
            self.dll.GetSettingData(ctypes.byref(bsetting), 0)
            H = bsetting.cycles
            if H == 0:
                H = 1
            data = np.empty((H, int(N / H)), dtype=np.uint32)

        else:
            data = np.empty((N,), dtype=np.uint32)

        p_type_ulong = ctypes.POINTER(ctypes.c_uint32)
        ptr = data.ctypes.data_as(p_type_ulong)
        self.dll.LVGetDat(ptr, 0)
        time_trace = np.int64(data)

        if self.gated and self.timetrace_tmp != []:
            time_trace = time_trace + self.timetrace_tmp

        info_dict = {'elapsed_sweeps': self.get_current_sweeps(),
                     'elapsed_time': None}  # self.get_current_runtime(), see qudi issue #487
        return time_trace, info_dict


    def get_data_testfile(self):
        """ Load data test file """
        data = np.loadtxt(os.path.join(get_main_dir(), 'tools', 'FastComTec_demo_timetrace.asc'))
        time.sleep(0.5)
        return data


    # =========================================================================
    #                           Non Interface methods
    # =========================================================================

    def get_bitshift(self):
        """Get bitshift from Fastcomtec.

        @return int settings.bitshift: the red out bitshift
        """

        settings = AcqSettings()
        self.dll.GetSettingData(ctypes.byref(settings), 0)
        return int(settings.bitshift)

    def set_bitshift(self, bitshift):
        """ Sets the bitshift properly for this card.

        @param int bitshift:

        @return int: asks the actual bitshift and returns the red out value
        """

        cmd = 'BITSHIFT={0}'.format(bitshift)
        self.dll.RunCmd(0, bytes(cmd, 'ascii'))
        return self.get_bitshift()

    def set_binwidth(self, binwidth):
        """ Set defined binwidth in Card.

        @param float binwidth: the current binwidth in seconds

        @return float: Red out bitshift converted to binwidth

        The binwidth is converted into to an appropiate bitshift defined as
        2**bitshift*minimal_binwidth.
        """
        bitshift = int(np.log2(binwidth/self.minimal_binwidth))
        self.set_bitshift(bitshift)

        return self.get_binwidth()

    def set_length(self, length_bins):
        """ Sets the length of the length of the actual measurement.

        @param int length_bins: Length of the measurement in bins

        @return float: Red out length of measurement
        """
        # First check if no constraint is
        constraints = self.get_constraints()
        if self.is_gated():
            cycles = self.get_cycles()
        else:
            cycles = 1
        if length_bins * cycles < constraints['max_bins']:
            # Smallest increment is 64 bins. Since it is better if the range is too short than too long, round down
            length_bins = int(64 * int(length_bins / 64))
            cmd = 'RANGE={0}'.format(int(length_bins))
            self.dll.RunCmd(0, bytes(cmd, 'ascii'))
            cmd = 'roimax={0}'.format(int(length_bins))        # needed? unused in mcs6
            self.dll.RunCmd(0, bytes(cmd, 'ascii'))

            # insert sleep time, otherwise fast counter crashed sometimes!
            time.sleep(0.5)
            return length_bins
        else:
            self.log.error('Dimensions {0} are too large for fast counter!'.format(length_bins * cycles))
            return -1


    def get_length(self):
        """ Get the length of the current measurement.

          @return int: length of the current measurement in bins
        """

        if self.is_gated():
            cycles = self.get_cycles()
            if cycles == 0:
                cycles = 1
        else:
            cycles = 1
        setting = AcqSettings()
        self.dll.GetSettingData(ctypes.byref(setting), 0)
        length = int(setting.range / cycles)

        return length

    def set_delay_start(self, delay_s):
        """ Sets the record delay length

        @param int delay_s: Record delay after receiving a start trigger
        @return int : specified delay in unit of bins
        """

        # A delay can only be adjusted in steps of 6.4ns
        delay_bins = np.rint(delay_s / 6.4e-9 /2.5)
        cmd = 'fstchan={0}'.format(int(delay_bins))
        self.dll.RunCmd(0, bytes(cmd, 'ascii'))
        return delay_bins

    def get_delay_start(self):
        """ Returns the current record delay length

        @return float delay_s: current record delay length in seconds
        """
        bsetting = AcqSettings()
        self.dll.GetSettingData(ctypes.byref(bsetting), 0)
        delay_s = bsetting.fstchan * 6.4e-9 * 2.5
        #prena = bsetting.prena

        return delay_s

    def _change_filename(self,name):
        """ Changed the name in FCT"""
        cmd = 'datname=%s'%name
        self.dll.RunCmd(0, bytes(cmd, 'ascii'))
        return name

    def change_save_mode(self, mode):
        """ Changes the save mode of p7887

        @param int mode: Specifies the save mode (0: No Save at Halt, 1: Save at Halt,
                        2: Write list file, No Save at Halt, 3: Write list file, Save at Halt

        @return int mode: specified save mode
        """
        cmd = 'savedata={0}'.format(mode)
        self.dll.RunCmd(0, bytes(cmd, 'ascii'))
        return mode

    def save_data(self, filename):
        """ save the current settings and data

        @param str filename: Location and name of the savefile
        """
        self._change_filename(filename)
        cmd = 'savempa'
        self.dll.RunCmd(0, bytes(cmd, 'ascii'))
        return filename


    # =========================================================================
    # Methods for gated counting
    # =========================================================================

    def configure_ssr_counter(self, counts_per_readout=None, countlength=None):
        # todo: this can now be done by .configure() -> change calling scripts or use this method as proxy
        self.change_sweep_mode(gated=True, cycles=countlength, n_sweeps_preset=counts_per_readout)
        self.set_sequences(1)
        time.sleep(0.1)
        return

    def change_sweep_mode(self, gated, cycles=None, n_sweeps_preset=None, is_single_sweeps=False):
        """
         Change the sweep mode (gated, ungated)

        @param bool gated: Gated or ungated
        @param int cycles: Optional, change number of cycles
        @param int n_sweeps_preset: Optional, number of sweeps until card stops or moves to next cycle
        """

        prena = 0
        if is_single_sweeps:
            prena += 6      # set bit 1,2. Atm: always use 'sweep preset'
        if gated:
            prena += 16     # set bit 4

        # Reduce length to prevent crashes
        if self.get_length() > 3000:
            self.set_length(64)
        if gated:
            self.set_cycle_mode(mode=True, cycles=cycles)
            self.set_preset_mode(mode=prena, preset=n_sweeps_preset)
            self.gated = True
        else:
            self.set_cycle_mode(mode=False, cycles=cycles)
            self.set_preset_mode(mode=prena, preset=n_sweeps_preset)
            self.gated = False

        self.log.debug("Changing sweep mode. Gated: {}, cycles: {}, n_sweeps: {}, single_sweeps: {}".format(
                        gated, cycles, n_sweeps_preset, is_single_sweeps))

        return gated

    def set_preset_mode(self, mode=16, preset=None):
        """ Turns on or off a specific preset mode

        @param int mode: O for off, 4 for sweep preset, 16 for start preset
        @param int preset: Optional, change number of presets

        @return just the input
        """

        # Specify preset mode
        cmd = 'prena={0}'.format(hex(mode))
        self.dll.RunCmd(0, bytes(cmd, 'ascii'))

        # Set the cycles if specified
        if preset is not None:
            self.set_preset(preset)

        return mode, preset

    def get_preset_mode(self):
        """ Gets the preset
        @return int mode: current preset
        """
        bsetting = AcqSettings()
        self.dll.GetSettingData(ctypes.byref(bsetting), 0)
        prena = bsetting.prena

        return prena


    def set_preset(self, preset):
        cmd = 'swpreset={0}'.format(preset)
        self.dll.RunCmd(0, bytes(cmd, 'ascii'))
        return preset

    def get_preset(self):
        """ Gets the preset
       @return int mode: current preset
        """
        bsetting = AcqSettings()
        self.dll.GetSettingData(ctypes.byref(bsetting), 0)
        preset = bsetting.swpreset
        return int(preset)

    def set_cycle_mode(self, mode=True, cycles=None, dma=False):
        """ Turns on or off the sequential cycle mode

        @param bool mode: Set or unset cycle mode
        @param int cycles: Optional, Change number of cycles

        @return: just the input
        """
        # todo: enabling dma breaks gated mode. Remove again?

        # First set cycles to 1 to prevent crashes
        if cycles == None:
            cycles_old = self.get_cycles()
        #self.set_cycles(1)
        # Turn on or off sequential cycle mode
        if mode:
            #if not self.get_cycle_mode() == 35528836:
            #cmd = 'sweepmode={0}'.format(hex(1978500))
            #cmd = 'sweepmode={0}'.format(hex(1974404))
            int_mode = 35528836
            if dma:
                int_mode += 32
            cmd = 'sweepmode={0}'.format(hex(int_mode))
            self.dll.RunCmd(0, bytes(cmd, 'ascii'))
        else:
            #if not self.get_cycle_mode() == 1978496:
            int_mode = 1978496
            if dma:
                int_mode += 32
            cmd = 'sweepmode={0}'.format(hex(int_mode))
            self.dll.RunCmd(0, bytes(cmd, 'ascii'))

        self.log.debug("Setting sweepmode to {}".format(int_mode))

        if not cycles == None:
            #self.set_cycles(cycles_old)
        #else:
            self.set_cycles(cycles)

        return mode, cycles

    def get_cycle_mode(self):
        """ Gets the cycles
        @return int mode: current cycles
        """
        bsetting = AcqSettings()
        self.dll.GetSettingData(ctypes.byref(bsetting), 0)
        sweepmode = bsetting.sweepmode
        return sweepmode

    def set_cycles(self, cycles):
        """ Sets the cycles

        @param int cycles: Total amount of cycles

        @return int mode: current cycles
        """
        # Check that no constraint is violated
        constraints = self.get_constraints()
        if cycles == 0:
            cycles = 1
        if self.get_length() * cycles < constraints['max_bins']:
            cmd = 'cycles={0}'.format(cycles)
            self.dll.RunCmd(0, bytes(cmd, 'ascii'))
            time.sleep(0.5)
            return cycles
        else:
            self.log.error('Dimensions {0} are too large for fast counter!'.format(self.get_length() * cycles))
            return -1

    def get_cycles(self):
        """ Gets the cycles
        @return int mode: current cycles
        """
        bsetting = AcqSettings()
        self.dll.GetSettingData(ctypes.byref(bsetting), 0)
        cycles = bsetting.cycles
        return cycles

    def set_sequences(self, sequences):
        """ Sets the cycles

        @param int cycles: Total amount of cycles

        @return int mode: current cycles
        """
        # Check that no constraint is violated
        self.log.debug("Setting sequences {}".format(sequences))

        cmd = 'sequences={0}'.format(sequences)
        self.dll.RunCmd(0, bytes(cmd, 'ascii'))
        return sequences

    def get_sequences(self):
        """ Gets the cycles
        @return int mode: current cycles
        """
        bsetting = AcqSettings()
        self.dll.GetSettingData(ctypes.byref(bsetting), 0)
        sequences = bsetting.sequences
        return sequences

    # =========================================================================
    #   The following methods have to be carefully reviewed and integrated as
    #   internal methods/function, because they might be important one day.
    # =========================================================================

    def SetDelay(self, t):
        #~ setting = AcqSettings()
        #~ self.dll.GetSettingData(ctypes.byref(setting), 0)
        #~ setting.fstchan = t/6.4
        #~ self.dll.StoreSettingData(ctypes.byref(setting), 0)
        #~ self.dll.NewSetting(0)
        self.dll.RunCmd(0, 'DELAY={0:f}'.format(t))
        return self.GetDelay()

    def GetDelay(self):
        setting = AcqSettings()
        self.dll.GetSettingData(ctypes.byref(setting), 0)
        return setting.fstchan * 6.4


    #former SaveData_fast
    def SaveData_locally(self, filename, laser_index):
        # os.chdir(r'D:\data\FastComTec')
        data = self.get_data()
        fil = open(filename + '.asc', 'w')
        for i in laser_index:
            for n in data[i:i+int(round(3000/(self.minimal_binwidth*2**self.GetBitshift())))
                    +int(round(1000/(self.minimal_binwidth*2**self.GetBitshift())))]:
                fil.write('{0!s}\n'.format(n))
        fil.close()

    def SetLevel(self, start, stop):
        setting = AcqSettings()
        self.dll.GetSettingData(ctypes.byref(setting), 0)
        def FloatToWord(r):
            return int((r+2.048)/4.096*int('ffff',16))
        setting.dac0 = ( setting.dac0 & int('ffff0000',16) ) | FloatToWord(start)
        setting.dac1 = ( setting.dac1 & int('ffff0000',16) ) | FloatToWord(stop)
        self.dll.StoreSettingData(ctypes.byref(setting), 0)
        self.dll.NewSetting(0)
        return self.GetLevel()

    def GetLevel(self):
        setting = AcqSettings()
        self.dll.GetSettingData(ctypes.byref(setting), 0)
        def WordToFloat(word):
            return (word & int('ffff',16)) * 4.096 / int('ffff',16) - 2.048
        return WordToFloat(setting.dac0), WordToFloat(setting.dac1)

    #used in one script for SSR
    #Todo: Remove
    def Running(self):
        s = self.GetStatus()
        return s.started

    def GetStatus(self):
        status = AcqStatus()
        self.dll.GetStatusData(ctypes.byref(status), 0)
        return status


    def load_setup(self, configname):
        cmd = 'loadcnf={0}'.format(configname)
        self.dll.RunCmd(0, bytes(cmd, 'ascii'))