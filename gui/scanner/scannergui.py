# -*- coding: utf-8 -*-

"""
This file contains the Qudi GUI for general Confocal control.

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
import os
import pyqtgraph as pg
import time

from core.connector import Connector
from core.statusvariable import StatusVar
from core.configoption import ConfigOption
from qtwidgets.scan_plotwidget import ScanImageItem
from qtwidgets.scientific_spinbox import ScienDSpinBox
from qtwidgets.slider import DoubleSlider
from qtwidgets.colorbar import ColorBarWidget
from gui.guibase import GUIBase
from gui.colordefs import ColorScaleInferno
from gui.colordefs import QudiPalettePale as palette
from gui.fitsettings import FitParametersWidget
from qtpy import QtCore
from qtpy import QtGui
from qtpy import QtWidgets
from qtpy import uic


class ConfocalMainWindow(QtWidgets.QMainWindow):
    """ Create the Mainwindow based on the corresponding *.ui file. """

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_scannergui.ui')

        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)
        return

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.action_utility_zoom.setChecked(not self.action_utility_zoom.isChecked())
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)
        return


class ScannerControlDockWidget(QtWidgets.QDockWidget):
    """ Create the scanner control dockwidget based on the corresponding *.ui file.
    """

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_scanner_control_widget.ui')

        super().__init__('Scanner Control')
        self.setObjectName('scanner_control_dockWidget')

        # Load UI file
        widget = QtWidgets.QWidget()
        uic.loadUi(ui_file, widget)
        widget.setObjectName('scanner_control_widget')

        self.setWidget(widget)
        return


class Scan2dDockWidget(QtWidgets.QDockWidget):
    """ Create the 2D scan dockwidget based on the corresponding *.ui file.
    """

    def __init__(self, axes_names):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_2d_scan_widget.ui')

        ax1 = axes_names[0][0].upper() + axes_names[0][1:]
        ax2 = axes_names[1][0].upper() + axes_names[1][1:]
        dock_title = '{0}-{1} Scan'.format(ax1, ax2)

        super().__init__(dock_title)
        self.setObjectName('{0}_{1}_scan_dockWidget'.format(*axes_names))

        # Load UI file
        widget = QtWidgets.QWidget()
        uic.loadUi(ui_file, widget)
        widget.setObjectName('{0}_{1}_scan_widget'.format(*axes_names))

        self.toggle_scan_button = widget.toggle_scan_pushButton
        self.channel_comboBox = widget.channel_comboBox
        self.channel_set = set()
        self.plot_widget = widget.image_scanPlotWidget
        self.colorbar = widget.colorbar_colorBarWidget
        self.image_item = ScanImageItem(image=np.zeros((2, 2)))
        self.plot_widget.addItem(self.image_item)
        self.colorbar.assign_image_item(self.image_item)

        self.setWidget(widget)
        return


class Scan1dDockWidget(QtWidgets.QDockWidget):
    """ Create the 1D scan dockwidget based on the corresponding *.ui file.
    """

    def __init__(self, axis_name):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_1d_scan_widget.ui')

        dock_title = '{0} Scan'.format(axis_name)

        super().__init__(dock_title)
        self.setObjectName('{0}_scan_dockWidget'.format(axis_name))

        # Load UI file
        widget = QtWidgets.QWidget()
        uic.loadUi(ui_file, widget)
        widget.setObjectName('{0}_scan_widget'.format(axis_name))

        self.toggle_scan_button = widget.toggle_scan_pushButton
        self.channel_comboBox = widget.channel_comboBox
        self.channel_set = set()
        self.plot_widget = widget.scan_plotWidget
        self.plot_item = pg.PlotDataItem(x=np.arange(2), y=np.zeros(2), pen=pg.mkPen(palette.c1))
        self.plot_widget.addItem(self.plot_item)

        self.setWidget(widget)
        return


class OptimizerDockWidget(QtWidgets.QDockWidget):
    """ Create the optimizer dockwidget based on the corresponding *.ui file.
    """

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_optimizer_widget.ui')

        super().__init__('Optimizer')
        self.setObjectName('optimizer_dockWidget')

        # Load UI file
        widget = QtWidgets.QWidget()
        uic.loadUi(ui_file, widget)
        widget.setObjectName('optimizer_widget')

        self.plot_widget = widget.optimizer_1d_plotWidget
        self.scan_widget = widget.optimizer_2d_scanPlotWidget
        self.axes_label = widget.optimizer_axes_label
        self.position_label = widget.optimizer_position_label
        self.image_item = ScanImageItem(image=np.zeros((2, 2)))
        self.plot_item = pg.PlotDataItem(x=np.arange(10),
                                         y=np.zeros(10),
                                         pen=pg.mkPen(palette.c1, style=QtCore.Qt.DotLine),
                                         symbol='o',
                                         symbolPen=palette.c1,
                                         symbolBrush=palette.c1,
                                         symbolSize=7)
        self.fit_plot_item = pg.PlotDataItem(x=np.arange(10),
                                             y=np.zeros(10),
                                             pen=pg.mkPen(palette.c2))
        self.plot_widget.addItem(self.plot_item)
        self.plot_widget.addItem(self.fit_plot_item)
        self.scan_widget.addItem(self.image_item)

        self.setWidget(widget)
        return


class TiltCorrectionDockWidget(QtWidgets.QDockWidget):
    """ Create the tilt correction dockwidget based on the corresponding *.ui file.
    """

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_tilt_correction_widget.ui')

        super().__init__('Tilt Correction')
        self.setObjectName('tilt_correction_dockWidget')

        # Load UI file
        widget = QtWidgets.QWidget()
        uic.loadUi(ui_file, widget)
        widget.setObjectName('tilt_correction_widget')

        widget.setMaximumWidth(widget.sizeHint().width())

        self.setWidget(widget)

        # FIXME: This widget needs to be redesigned for arbitrary axes. Disable it for now.
        self.widget().setEnabled(False)
        return


class ScannerSettingDialog(QtWidgets.QDialog):
    """ Create the ScannerSettingsDialog window, based on the corresponding *.ui file."""

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_scanner_settings.ui')

        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)
        return


class OptimizerSettingDialog(QtWidgets.QDialog):
    """ User configurable settings for the optimizer embedded in cofocal gui"""

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_optimizer_settings.ui')

        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)
        return


class ScannerGui(GUIBase):
    """ Main Confocal Class for xy and depth scans.
    """
    _modclass = 'ScannerGui'
    _modtype = 'gui'

    # declare connectors
    scanninglogic = Connector(interface='ScanningLogic')

    # config options for gui
    image_axes_padding = ConfigOption(name='image_axes_padding', default=0.02)
    default_position_unit_prefix = ConfigOption(name='default_position_unit_prefix', default=None)

    # status vars
    slider_small_step = StatusVar(name='slider_small_step', default=10e-9)
    slider_big_step = StatusVar(name='slider_big_step', default=100e-9)
    _show_true_scanner_position = StatusVar(name='show_true_scanner_position', default=False)
    _window_state = StatusVar(name='window_state', default=None)
    _window_geometry = StatusVar(name='window_geometry', default=None)

    # signals
    sigMoveScannerPosition = QtCore.Signal(dict, object)
    sigScannerSettingsChanged = QtCore.Signal(dict)
    sigOptimizerSettingsChanged = QtCore.Signal(dict)
    sigToggleScan = QtCore.Signal(tuple, bool)

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

        # QMainWindow and QDialog child instances
        self._mw = None
        self._ssd = None
        self._osd = None

        # References to automatically generated GUI elements
        self.axes_control_widgets = None
        self.optimizer_settings_axes_widgets = None
        self.scan_2d_dockwidgets = None
        self.scan_1d_dockwidgets = None

        # References to static dockwidgets
        self.optimizer_dockwidget = None
        self.tilt_correction_dockwidget = None
        self.scanner_control_dockwidget = None
        return

    def on_activate(self):
        """ Initializes all needed UI files and establishes the connectors.

        This method executes the all the inits for the differnt GUIs and passes
        the event argument from fysom to the methods.
        """
        self.scan_2d_dockwidgets = dict()
        self.scan_1d_dockwidgets = dict()

        # Initialize main window and dialogues
        self._ssd = ScannerSettingDialog()
        self._mw = ConfocalMainWindow()

        # Initialize fixed dockwidgets
        self._init_static_dockwidgets()

        # Initialize dialog windows
        self._init_optimizer_settings()

        # Configure widgets according to available scan axes
        self._generate_axes_control_widgets()

        # Set input widget value ranges and units according to scanner constraints
        self.apply_scanner_constraints()

        # Initialize widget data
        self.update_scanner_settings()
        self.scanner_target_updated()
        self.scanner_position_updated()
        self.scan_data_updated()

        # Initialize dockwidgets to default view
        self.restore_default_view()
        # Try to restore window state and geometry
        if self._window_geometry is not None:
            if not self._mw.restoreGeometry(bytearray.fromhex(self._window_geometry)):
                self._window_geometry = None
                self.log.debug(
                    'Unable to restore previous window geometry. Falling back to default.')
        if self._window_state is not None:
            if not self._mw.restoreState(bytearray.fromhex(self._window_state)):
                self._window_state = None
                self.log.debug(
                    'Unable to restore previous window state. Falling back to default.')

        # Connect signals
        self._mw.action_restore_default_view.triggered.connect(self.restore_default_view)

        self.sigMoveScannerPosition.connect(
            self.scanninglogic().set_scanner_target_position, QtCore.Qt.QueuedConnection)
        self.sigScannerSettingsChanged.connect(
            self.scanninglogic().set_scanner_settings, QtCore.Qt.QueuedConnection)
        self.sigOptimizerSettingsChanged.connect(
            self.scanninglogic().set_optimizer_settings, QtCore.Qt.QueuedConnection)
        self.sigToggleScan.connect(self.scanninglogic().toggle_scan, QtCore.Qt.QueuedConnection)

        self._mw.action_history_forward.triggered.connect(
            self.scanninglogic().history_forward, QtCore.Qt.QueuedConnection)
        self._mw.action_history_back.triggered.connect(
            self.scanninglogic().history_backwards, QtCore.Qt.QueuedConnection)
        self._mw.action_utility_full_range.triggered.connect(
            self.scanninglogic().set_full_scan_ranges, QtCore.Qt.QueuedConnection)
        self._mw.action_utility_zoom.toggled.connect(self.toggle_cursor_zoom)

        self.scanninglogic().sigScannerPositionChanged.connect(
            self.scanner_position_updated, QtCore.Qt.QueuedConnection)
        self.scanninglogic().sigScannerTargetChanged.connect(
            self.scanner_target_updated, QtCore.Qt.QueuedConnection)
        self.scanninglogic().sigScannerSettingsChanged.connect(
            self.update_scanner_settings, QtCore.Qt.QueuedConnection)
        self.scanninglogic().sigOptimizerSettingsChanged.connect(
            self.update_optimizer_settings, QtCore.Qt.QueuedConnection)
        self.scanninglogic().sigScanDataChanged.connect(
            self.scan_data_updated, QtCore.Qt.QueuedConnection)
        self.scanninglogic().sigScanStateChanged.connect(
            self.scan_state_updated, QtCore.Qt.QueuedConnection)

        self.show()
        return

    def on_deactivate(self):
        """ Reverse steps of activation

        @return int: error code (0:OK, -1:error)
        """
        self._mw.action_restore_default_view.triggered.disconnect()

        self.sigMoveScannerPosition.disconnect()
        self.sigScannerSettingsChanged.disconnect()
        self.sigOptimizerSettingsChanged.disconnect()
        self.sigToggleScan.disconnect()
        self._mw.action_history_forward.triggered.disconnect()
        self._mw.action_history_back.triggered.disconnect()
        self._mw.action_utility_full_range.triggered.disconnect()
        self._mw.action_utility_zoom.toggled.disconnect()
        self.scanninglogic().sigScannerPositionChanged.disconnect()
        self.scanninglogic().sigScannerTargetChanged.disconnect()
        self.scanninglogic().sigScannerSettingsChanged.disconnect()
        self.scanninglogic().sigOptimizerSettingsChanged.disconnect()
        self.scanninglogic().sigScanDataChanged.disconnect()
        self.scanninglogic().sigScanStateChanged.disconnect()

        self._window_geometry = bytearray(self._mw.saveGeometry()).hex()
        self._window_state = bytearray(self._mw.saveState()).hex()
        self._mw.close()
        return 0

    def show(self):
        """Make main window visible and put it above all other windows. """
        # Show the Main Confocal GUI:
        self._mw.show()
        self._mw.activateWindow()
        self._mw.raise_()

    def _init_optimizer_settings(self):
        """ Configuration and initialisation of the optimizer settings dialog.
        """
        # Create the Settings window
        self._osd = OptimizerSettingDialog()

        # Connect MainWindow actions
        self._mw.action_optimizer_settings.triggered.connect(lambda x: self._osd.exec_())

        # Create dynamically created widgets
        self._generate_optimizer_axes_widgets()

        # Connect the action of the settings window with the code:
        self._osd.accepted.connect(self.change_optimizer_settings)
        self._osd.rejected.connect(self.update_optimizer_settings)
        self._osd.buttonBox.button(QtWidgets.QDialogButtonBox.Apply).clicked.connect(
            self.change_optimizer_settings)

        # initialize widget content
        self.update_optimizer_settings()
        return

    def _init_static_dockwidgets(self):
        self.optimizer_dockwidget = OptimizerDockWidget()
        self.optimizer_dockwidget.setAllowedAreas(QtCore.Qt.TopDockWidgetArea)
        self.optimizer_dockwidget.scan_widget.add_crosshair(movable=False,
                                                            pen={'color': '#00ff00', 'width': 2})
        self.optimizer_dockwidget.scan_widget.setAspectLocked(lock=True, ratio=1.0)
        self.optimizer_dockwidget.visibilityChanged.connect(
            self._mw.action_view_optimizer.setChecked)
        self._mw.action_view_optimizer.triggered[bool].connect(
            self.optimizer_dockwidget.setVisible)
        self.tilt_correction_dockwidget = TiltCorrectionDockWidget()
        self.tilt_correction_dockwidget.setAllowedAreas(QtCore.Qt.BottomDockWidgetArea)
        self.tilt_correction_dockwidget.visibilityChanged.connect(
            self._mw.action_view_tilt_correction.setChecked)
        self._mw.action_view_tilt_correction.triggered[bool].connect(
            self.tilt_correction_dockwidget.setVisible)
        self.scanner_control_dockwidget = ScannerControlDockWidget()
        self.scanner_control_dockwidget.setAllowedAreas(QtCore.Qt.BottomDockWidgetArea)
        self.scanner_control_dockwidget.visibilityChanged.connect(
            self._mw.action_view_scanner_control.setChecked)
        self._mw.action_view_scanner_control.triggered[bool].connect(
            self.scanner_control_dockwidget.setVisible)

    def _generate_axes_control_widgets(self):
        font = QtGui.QFont()
        font.setBold(True)
        layout = self.scanner_control_dockwidget.widget().layout()

        self.axes_control_widgets = dict()
        for index, axis_name in enumerate(self.scanninglogic().scanner_axes_names, 1):
            label = QtWidgets.QLabel('{0}-Axis:'.format(axis_name))
            label.setObjectName('{0}_axis_label'.format(axis_name))
            label.setFont(font)
            label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

            res_spinbox = QtWidgets.QSpinBox()
            res_spinbox.setObjectName('{0}_resolution_spinBox'.format(axis_name))
            res_spinbox.setRange(2, 2 ** 31 - 1)
            res_spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
            res_spinbox.setMinimumSize(50, 0)
            res_spinbox.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                      QtWidgets.QSizePolicy.Preferred)

            min_spinbox = ScienDSpinBox()
            min_spinbox.setObjectName('{0}_min_range_scienDSpinBox'.format(axis_name))
            min_spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
            min_spinbox.setMinimumSize(75, 0)
            min_spinbox.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                      QtWidgets.QSizePolicy.Preferred)

            max_spinbox = ScienDSpinBox()
            max_spinbox.setObjectName('{0}_max_range_scienDSpinBox'.format(axis_name))
            max_spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
            max_spinbox.setMinimumSize(75, 0)
            max_spinbox.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                      QtWidgets.QSizePolicy.Preferred)

            slider = DoubleSlider(QtCore.Qt.Horizontal)
            slider.setObjectName('{0}_position_doubleSlider'.format(axis_name))
            slider.setMinimumSize(150, 0)
            slider.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

            pos_spinbox = ScienDSpinBox()
            pos_spinbox.setObjectName('{0}_position_scienDSpinBox'.format(axis_name))
            pos_spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
            pos_spinbox.setMinimumSize(75, 0)
            pos_spinbox.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                      QtWidgets.QSizePolicy.Preferred)

            # Add to layout
            layout.addWidget(label, index, 0)
            layout.addWidget(res_spinbox, index, 1)
            layout.addWidget(min_spinbox, index, 3)
            layout.addWidget(max_spinbox, index, 4)
            layout.addWidget(slider, index, 6)
            layout.addWidget(pos_spinbox, index, 7)

            # Remember widgets references for later access
            self.axes_control_widgets[axis_name] = dict()
            self.axes_control_widgets[axis_name]['label'] = label
            self.axes_control_widgets[axis_name]['res_spinbox'] = res_spinbox
            self.axes_control_widgets[axis_name]['min_spinbox'] = min_spinbox
            self.axes_control_widgets[axis_name]['max_spinbox'] = max_spinbox
            self.axes_control_widgets[axis_name]['slider'] = slider
            self.axes_control_widgets[axis_name]['pos_spinbox'] = pos_spinbox

        # layout.removeWidget(line)
        layout.addWidget(self.scanner_control_dockwidget.widget().line, 0, 2, -1, 1)
        layout.addWidget(self.scanner_control_dockwidget.widget().line_2, 0, 5, -1, 1)
        layout.setColumnStretch(5, 1)
        self.scanner_control_dockwidget.widget().setMaximumHeight(
            self.scanner_control_dockwidget.widget().sizeHint().height())

        # Connect signals
        for axis, widget_dict in self.axes_control_widgets.items():
            widget_dict['min_spinbox'].editingFinished.connect(self.change_scan_range)
            widget_dict['max_spinbox'].editingFinished.connect(self.change_scan_range)
            widget_dict['res_spinbox'].editingFinished.connect(self.change_scan_resolution)
            widget_dict['slider'].valueChanged.connect(
                self.__get_slider_update_func(axis, widget_dict['slider']))
            widget_dict['pos_spinbox'].editingFinished.connect(
                self.__get_target_spinbox_update_func(axis, widget_dict['pos_spinbox']))
        return

    def _generate_optimizer_axes_widgets(self):
        font = QtGui.QFont()
        font.setBold(True)
        layout = self._osd.scan_ranges_gridLayout

        self.optimizer_settings_axes_widgets = dict()
        for index, axis_name in enumerate(self.scanninglogic().scanner_axes_names, 1):
            label = QtWidgets.QLabel('{0}-Axis:'.format(axis_name))
            label.setFont(font)
            label.setAlignment(QtCore.Qt.AlignRight)

            range_spinbox = ScienDSpinBox()
            range_spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
            range_spinbox.setMinimumSize(70, 0)
            range_spinbox.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                        QtWidgets.QSizePolicy.Preferred)

            res_spinbox = QtWidgets.QSpinBox()
            res_spinbox.setRange(2, 2 ** 31 - 1)
            res_spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
            res_spinbox.setMinimumSize(70, 0)
            res_spinbox.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                      QtWidgets.QSizePolicy.Preferred)

            # Add to layout
            layout.addWidget(label, index, 0)
            layout.addWidget(range_spinbox, index, 1)
            layout.addWidget(res_spinbox, index, 2)

            # Remember widgets references for later access
            self.optimizer_settings_axes_widgets[axis_name] = dict()
            self.optimizer_settings_axes_widgets[axis_name]['label'] = label
            self.optimizer_settings_axes_widgets[axis_name]['range_spinbox'] = range_spinbox
            self.optimizer_settings_axes_widgets[axis_name]['res_spinbox'] = res_spinbox
        return

    @QtCore.Slot()
    def restore_default_view(self):
        """ Restore the arrangement of DockWidgets to default """
        self._mw.setDockNestingEnabled(True)

        # Handle dynamically created dock widgets
        for i, dockwidget in enumerate(self.scan_2d_dockwidgets.values()):
            dockwidget.show()
            dockwidget.setFloating(False)
            self._mw.addDockWidget(QtCore.Qt.TopDockWidgetArea, dockwidget)
            if i > 1:
                first_dockwidget = self.scan_2d_dockwidgets[list(self.scan_2d_dockwidgets)[0]]
                self._mw.tabifyDockWidget(first_dockwidget, dockwidget)
        for i, dockwidget in enumerate(self.scan_1d_dockwidgets.values()):
            dockwidget.show()
            dockwidget.setFloating(False)
            self._mw.addDockWidget(QtCore.Qt.TopDockWidgetArea, dockwidget)
            if i > 0:
                first_dockwidget = self.scan_1d_dockwidgets[list(self.scan_1d_dockwidgets)[0]]
                self._mw.tabifyDockWidget(first_dockwidget, dockwidget)

        # Handle static dock widgets
        self.optimizer_dockwidget.setFloating(False)
        self.optimizer_dockwidget.show()
        self._mw.addDockWidget(QtCore.Qt.TopDockWidgetArea, self.optimizer_dockwidget)
        if self.scan_1d_dockwidgets:
            dockwidget = self.scan_1d_dockwidgets[list(self.scan_1d_dockwidgets)[0]]
            if self.scan_2d_dockwidgets:
                self._mw.splitDockWidget(dockwidget, self.optimizer_dockwidget, QtCore.Qt.Vertical)
            if len(self.scan_2d_dockwidgets) > 1:
                dock_list = [self.scan_2d_dockwidgets[list(self.scan_2d_dockwidgets)[0]],
                             self.scan_2d_dockwidgets[list(self.scan_2d_dockwidgets)[1]],
                             dockwidget]
                self._mw.resizeDocks(dock_list, [1, 1, 1], QtCore.Qt.Horizontal)
            elif self.scan_2d_dockwidgets:
                dock_list = [self.scan_2d_dockwidgets[list(self.scan_2d_dockwidgets)[0]],
                             dockwidget]
                self._mw.resizeDocks(dock_list, [1, 1], QtCore.Qt.Horizontal)
            else:
                dock_list = [dockwidget, self.optimizer_dockwidget]
                self._mw.resizeDocks(dock_list, [1, 1], QtCore.Qt.Horizontal)
        elif len(self.scan_2d_dockwidgets) > 1:
            dockwidget = self.scan_2d_dockwidgets[list(self.scan_2d_dockwidgets)[1]]
            self._mw.splitDockWidget(dockwidget, self.optimizer_dockwidget, QtCore.Qt.Vertical)
            dock_list = [self.scan_2d_dockwidgets[list(self.scan_2d_dockwidgets)[0]],
                         dockwidget]
            self._mw.resizeDocks(dock_list, [1, 1], QtCore.Qt.Horizontal)
        else:
            dock_list = [self.scan_2d_dockwidgets[list(self.scan_2d_dockwidgets)[0]],
                         self.optimizer_dockwidget]
            self._mw.resizeDocks(dock_list, [1, 1], QtCore.Qt.Horizontal)

        self.scanner_control_dockwidget.setFloating(False)
        self.scanner_control_dockwidget.show()
        self._mw.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.scanner_control_dockwidget)
        self.tilt_correction_dockwidget.setFloating(False)
        self.tilt_correction_dockwidget.hide()
        self._mw.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.tilt_correction_dockwidget)
        return

    def apply_scanner_constraints(self):
        """ Set limits on input widgets according to scanner hardware constraints. """
        constraints = self.scanninglogic().scanner_constraints['axes']

        # Apply constraints for every scannner axis
        for index, (axis, axis_dict) in enumerate(constraints.items()):
            # Set value ranges
            res_range = (max(2, axis_dict['min_resolution']),
                         min(2 ** 31 - 1, axis_dict['max_resolution']))
            self.axes_control_widgets[axis]['res_spinbox'].setRange(*res_range)
            self.axes_control_widgets[axis]['min_spinbox'].setRange(axis_dict['min_value'],
                                                                    axis_dict['max_value'])
            self.axes_control_widgets[axis]['max_spinbox'].setRange(axis_dict['min_value'],
                                                                    axis_dict['max_value'])
            self.axes_control_widgets[axis]['pos_spinbox'].setRange(axis_dict['min_value'],
                                                                    axis_dict['max_value'])
            self.axes_control_widgets[axis]['slider'].setRange(axis_dict['min_value'],
                                                               axis_dict['max_value'])
            self.axes_control_widgets[axis]['slider'].set_granularity(
                round(
                    (axis_dict['max_value'] - axis_dict['min_value']) / axis_dict['min_step']) + 1)
            self.optimizer_settings_axes_widgets[axis]['range_spinbox'].setRange(
                0, axis_dict['max_value'] - axis_dict['min_value'])
            self.optimizer_settings_axes_widgets[axis]['res_spinbox'].setRange(*res_range)
            # Set units as SpinBox suffix
            self.axes_control_widgets[axis]['min_spinbox'].setSuffix(axis_dict['unit'])
            self.axes_control_widgets[axis]['max_spinbox'].setSuffix(axis_dict['unit'])
            self.axes_control_widgets[axis]['pos_spinbox'].setSuffix(axis_dict['unit'])
            self.optimizer_settings_axes_widgets[axis]['range_spinbox'].setSuffix(axis_dict['unit'])

        # FIXME: Apply general scanner constraints
        return

    def _remove_scan_dockwidget(self, axes):
        if axes in self.scan_1d_dockwidgets:
            self._mw.removeDockWidget(self.scan_1d_dockwidgets[axes])
            del self.scan_1d_dockwidgets[axes]
        elif axes in self.scan_2d_dockwidgets:
            self._mw.removeDockWidget(self.scan_2d_dockwidgets[axes])
            del self.scan_2d_dockwidgets[axes]
        return

    def _add_scan_dockwidget(self, axes):
        scanner_constraints = self.scanninglogic().scanner_constraints['axes']
        optimizer_settings = self.scanninglogic().optimizer_settings
        axes = tuple(axes)
        if len(axes) == 1:
            dockwidget = Scan1dDockWidget(axes[0])
            dockwidget.setAllowedAreas(QtCore.Qt.TopDockWidgetArea)
            self.scan_1d_dockwidgets[axes] = dockwidget
            self._mw.addDockWidget(QtCore.Qt.TopDockWidgetArea, dockwidget)
            # Set axis labels
            dockwidget.plot_widget.setLabel('bottom',
                                            axes[0],
                                            units=scanner_constraints[axes[0]]['unit'])
            dockwidget.plot_widget.setLabel('left', 'scan data', units='arb.u.')
            dockwidget.toggle_scan_button.clicked.connect(self.__get_toggle_scan_func(axes))
        else:
            dockwidget = Scan2dDockWidget(axes)
            dockwidget.setAllowedAreas(QtCore.Qt.TopDockWidgetArea)
            self.scan_2d_dockwidgets[axes] = dockwidget
            self._mw.addDockWidget(QtCore.Qt.TopDockWidgetArea, dockwidget)
            # Set axis labels
            dockwidget.plot_widget.setLabel(
                'bottom', axes[0], units=scanner_constraints[axes[0]]['unit'])
            dockwidget.plot_widget.setLabel(
                'left', axes[1], units=scanner_constraints[axes[1]]['unit'])
            dockwidget.plot_widget.add_crosshair(movable=True, min_size_factor=0.02)
            dockwidget.plot_widget.add_crosshair(movable=False,
                                                 pen={'color': '#00ffff', 'width': 1})
            dockwidget.plot_widget.bring_crosshair_on_top(0)
            dockwidget.plot_widget.crosshairs[0].set_allowed_range(
                ((scanner_constraints[axes[0]]['min_value'],
                  scanner_constraints[axes[0]]['max_value']),
                 (scanner_constraints[axes[1]]['min_value'],
                  scanner_constraints[axes[1]]['max_value'])))
            dockwidget.plot_widget.crosshairs[0].set_size(
                (optimizer_settings['axes'][axes[0]]['range'],
                 optimizer_settings['axes'][axes[1]]['range']))
            if not self.show_true_scanner_position:
                dockwidget.plot_widget.hide_crosshair(1)
            dockwidget.plot_widget.setAspectLocked(lock=True, ratio=1.0)
            dockwidget.plot_widget.toggle_zoom_by_selection(True)
            dockwidget.plot_widget.crosshairs[0].sigDraggedPosChanged.connect(
                self.__get_crosshair_update_func(axes, dockwidget.plot_widget.crosshairs[0]))
            dockwidget.toggle_scan_button.clicked.connect(self.__get_toggle_scan_func(tuple(axes)))
            dockwidget.plot_widget.sigMouseAreaSelected.connect(
                self.__get_range_from_selection_func(tuple(axes)))
            dockwidget.channel_comboBox.currentIndexChanged.connect(
                self.__get_data_channel_changed_func(tuple(axes)))
        return

    @property
    def show_true_scanner_position(self):
        return self._show_true_scanner_position

    @show_true_scanner_position.setter
    def show_true_scanner_position(self, show):
        self.toggle_true_scanner_position_display(show)

    @QtCore.Slot(bool)
    def toggle_true_scanner_position_display(self, show):
        show = bool(show)
        if show == self._show_true_scanner_position:
            return
        self._show_true_scanner_position = show
        if self._show_true_scanner_position:
            for dockwidget in self.scan_2d_dockwidgets.values():
                dockwidget.plot_widget.show_crosshair(1)
        else:
            for dockwidget in self.scan_2d_dockwidgets.values():
                dockwidget.plot_widget.hide_crosshair(1)
        return

    @QtCore.Slot()
    @QtCore.Slot(dict)
    def update_scanner_settings(self, settings=None):
        """
        Update scanner settings from logic and set widgets accordingly.

        @param dict settings: Settings dict containing the scanner settings to update.
                              If None (default) read the scanner setting from logic and update.
        """
        if not isinstance(settings, dict):
            settings = self.scanninglogic().scanner_settings

        if 'pixel_clock_frequency' in settings:
            self._ssd.pixel_clock_frequency_scienSpinBox.setValue(settings['pixel_clock_frequency'])
        if 'backscan_points' in settings:
            self._ssd.backscan_speed_scienSpinBox.setValue(settings['backscan_points'])
        if 'scan_resolution' in settings:
            for axis, resolution in settings['scan_resolution'].items():
                res_spinbox = self.axes_control_widgets[axis]['res_spinbox']
                res_spinbox.blockSignals(True)
                res_spinbox.setValue(resolution)
                res_spinbox.blockSignals(False)
        if 'scan_range' in settings:
            for axis, axis_range in settings['scan_range'].items():
                min_spinbox = self.axes_control_widgets[axis]['min_spinbox']
                max_spinbox = self.axes_control_widgets[axis]['max_spinbox']
                min_spinbox.blockSignals(True)
                max_spinbox.blockSignals(True)
                min_spinbox.setValue(axis_range[0])
                max_spinbox.setValue(axis_range[1])
                min_spinbox.blockSignals(False)
                max_spinbox.blockSignals(False)
        if 'scan_axes' in settings:
            present_keys = set(self.scan_1d_dockwidgets)
            present_keys.update(set(self.scan_2d_dockwidgets))

            # Remove obsolete scan dockwidgets and images items
            keys_to_delete = present_keys.difference(settings['scan_axes'])
            for key in keys_to_delete:
                self._remove_scan_dockwidget(key)

            # Add new dockwidgets and image items, do not use set to keep ordering
            keys_to_add = [key for key in settings['scan_axes'] if key not in present_keys]
            for key in keys_to_add:
                self._add_scan_dockwidget(key)
        return

    def move_scanner_position(self, target_pos):
        """

        @param dict target_pos:
        """
        self.sigMoveScannerPosition.emit(target_pos, id(self))

    @QtCore.Slot(dict)
    @QtCore.Slot(dict, object)
    def scanner_position_updated(self, pos_dict=None, caller_id=None):
        """
        Updates the scanner position and set widgets accordingly.

        @param dict pos_dict: The scanner position dict to update each axis position.
                              If None (default) read the scanner position from logic and update.
        @param int caller_id: The qudi module object id responsible for triggering this update
        """
        # If this update has been issued by this module, do not update display.
        # This has already been done.
        if caller_id == id(self):
            return

        if not isinstance(pos_dict, dict):
            pos_dict = self.scanninglogic().scanner_position

        self._update_position_display(pos_dict)
        return

    @QtCore.Slot(dict)
    @QtCore.Slot(dict, object)
    def scanner_target_updated(self, pos_dict=None, caller_id=None):
        """
        Updates the scanner target and set widgets accordingly.

        @param dict pos_dict: The scanner position dict to update each axis position.
                              If None (default) read the scanner position from logic and update.
        @param int caller_id: The qudi module object id responsible for triggering this update
        """
        # If this update has been issued by this module, do not update display.
        # This has already been done.
        if caller_id == id(self):
            return

        if not isinstance(pos_dict, dict):
            pos_dict = self.scanninglogic().scanner_position

        self._update_target_display(pos_dict)
        return

    @QtCore.Slot()
    @QtCore.Slot(dict)
    def scan_data_updated(self, scan_data=None):
        """

        @param dict scan_data:
        """
        if not isinstance(scan_data, dict):
            scan_data = self.scanninglogic().scan_data

        for axes, data in scan_data.items():
            if len(axes) == 2:
                dockwidget = self.scan_2d_dockwidgets[axes]
                if set(data.channel_names) != dockwidget.channel_set:
                    old_channel = dockwidget.channel_comboBox.currentText()
                    dockwidget.channel_comboBox.blockSignals(True)
                    dockwidget.channel_comboBox.clear()
                    dockwidget.channel_comboBox.addItems(data.channel_names)
                    dockwidget.channel_set = set(data.channel_names)
                    if old_channel in dockwidget.channel_set:
                        dockwidget.channel_comboBox.setCurrentText(old_channel)
                    dockwidget.channel_comboBox.blockSignals(False)
                channel = dockwidget.channel_comboBox.currentText()
                dockwidget.image_item.setImage(image=data.data[channel])
                data_ranges_x, data_ranges_y = data.target_ranges
                px_size_x = abs(data_ranges_x[1] - data_ranges_x[0]) / data.resolution[0]
                px_size_y = abs(data_ranges_y[1] - data_ranges_y[0]) / data.resolution[1]
                x_min = min(data_ranges_x) - px_size_x / 2
                x_max = max(data_ranges_x) + px_size_x / 2
                y_min = min(data_ranges_y) - px_size_y / 2
                y_max = max(data_ranges_y) + px_size_y / 2
                dockwidget.image_item.set_image_extent(((x_min, x_max), (y_min, y_max)))
                dockwidget.colorbar.set_label(text='scan data', unit=data.channel_units[channel])
            elif len(axes) == 1:
                dockwidget = self.scan_1d_dockwidgets[axes]
                if set(data.channel_names) != dockwidget.channel_set:
                    old_channel = dockwidget.channel_comboBox.currentText()
                    dockwidget.channel_comboBox.clear()
                    dockwidget.channel_comboBox.addItems(data.channel_names)
                    dockwidget.channel_set = set(data.channel_names)
                    if old_channel in dockwidget.channel_set:
                        dockwidget.channel_comboBox.setCurrentText(old_channel)
                channel = dockwidget.channel_comboBox.currentText()
                dockwidget.plot_item.setData(
                    np.linspace(*(data.target_ranges[0]), data.data[channel].size),
                    data.data[channel])
                dockwidget.plot_widget.setLabel(
                    'left', 'scan data', units=data.channel_units[channel])
        return

    @QtCore.Slot(bool, tuple)
    def scan_state_updated(self, is_running, scan_axes):
        if is_running:
            for axes, dockwidget in self.scan_2d_dockwidgets.items():
                if axes == scan_axes:
                    dockwidget.toggle_scan_button.setChecked(True)
                else:
                    dockwidget.toggle_scan_button.setEnabled(False)
            for axes, dockwidget in self.scan_1d_dockwidgets.items():
                if axes == scan_axes:
                    dockwidget.toggle_scan_button.setChecked(True)
                else:
                    dockwidget.toggle_scan_button.setEnabled(False)
        else:
            for axes, dockwidget in self.scan_2d_dockwidgets.items():
                if axes == scan_axes:
                    dockwidget.toggle_scan_button.setChecked(False)
                else:
                    dockwidget.toggle_scan_button.setEnabled(True)
            for axes, dockwidget in self.scan_1d_dockwidgets.items():
                if axes == scan_axes:
                    dockwidget.toggle_scan_button.setChecked(False)
                else:
                    dockwidget.toggle_scan_button.setEnabled(True)
        return

    def _update_position_display(self, pos_dict):
        """

        @param dict pos_dict:
        """
        for axis, pos in pos_dict.items():
            for axes, dockwidget in self.scan_2d_dockwidgets.items():
                crosshair = dockwidget.plot_widget.crosshairs[1]
                ax1, ax2 = axes
                if ax1 == axis:
                    crosshair_pos = (pos, crosshair.position[1])
                    crosshair.set_position(crosshair_pos)
                elif ax2 == axis:
                    crosshair_pos = (crosshair.position[0], pos)
                    crosshair.set_position(crosshair_pos)
        return

    def _update_target_display(self, pos_dict, exclude_widget=None):
        """

        @param dict pos_dict:
        @param object exclude_widget:
        """
        for axis, pos in pos_dict.items():
            spinbox = self.axes_control_widgets[axis]['pos_spinbox']
            if exclude_widget is not spinbox:
                spinbox.blockSignals(True)
                spinbox.setValue(pos)
                spinbox.blockSignals(False)
            slider = self.axes_control_widgets[axis]['slider']
            if exclude_widget is not slider:
                slider.blockSignals(True)
                slider.setValue(pos)
                slider.blockSignals(False)
            for axes, dockwidget in self.scan_2d_dockwidgets.items():
                crosshair = dockwidget.plot_widget.crosshairs[0]
                if crosshair is exclude_widget:
                    continue
                ax1, ax2 = axes
                if ax1 == axis:
                    crosshair_pos = (pos, crosshair.position[1])
                    crosshair.set_position(crosshair_pos)
                elif ax2 == axis:
                    crosshair_pos = (crosshair.position[0], pos)
                    crosshair.set_position(crosshair_pos)
        return

    def __get_slider_update_func(self, ax, slider):
        def update_func(x):
            pos_dict = {ax: x}
            self._update_target_display(pos_dict, exclude_widget=slider)
            self.move_scanner_position(pos_dict)
        return update_func

    def __get_target_spinbox_update_func(self, ax, spinbox):
        def update_func():
            pos_dict = {ax: spinbox.value()}
            self._update_target_display(pos_dict, exclude_widget=spinbox)
            self.move_scanner_position(pos_dict)
        return update_func

    def __get_crosshair_update_func(self, ax, crosshair):
        def update_func(x, y):
            pos_dict = {ax[0]: x, ax[1]: y}
            self._update_target_display(pos_dict, exclude_widget=crosshair)
            self.move_scanner_position(pos_dict)
        return update_func

    def __get_toggle_scan_func(self, ax):
        return lambda enabled: self.sigToggleScan.emit(ax, enabled)

    def __get_range_from_selection_func(self, ax):
        def set_range_func(qrect):
            x_min, x_max = min(qrect.left(), qrect.right()), max(qrect.left(), qrect.right())
            y_min, y_max = min(qrect.top(), qrect.bottom()), max(qrect.top(), qrect.bottom())
            self.sigScannerSettingsChanged.emit({'scan_range': {ax[0]: (x_min, x_max),
                                                                ax[1]: (y_min, y_max)}})
            self._mw.action_utility_zoom.setChecked(False)
        return set_range_func

    def __get_data_channel_changed_func(self, ax):
        def set_data_channel():
            self.scan_data_updated({ax: self.scanninglogic().scan_data[ax]})
        return set_data_channel

    @QtCore.Slot()
    def change_scan_range(self):
        obj_name = self.sender().objectName()
        if not obj_name.endswith('_range_scienDSpinBox'):
            return
        axis = obj_name.rsplit('_', 3)[0]
        scan_range = (self.axes_control_widgets[axis]['min_spinbox'].value(),
                      self.axes_control_widgets[axis]['max_spinbox'].value())
        self.sigScannerSettingsChanged.emit({'scan_range': {axis: scan_range}})
        return

    @QtCore.Slot()
    def change_scan_resolution(self):
        obj_name = self.sender().objectName()
        if not obj_name.endswith('_resolution_spinBox'):
            return
        axis = obj_name.rsplit('_', 2)[0]
        scan_res = self.axes_control_widgets[axis]['res_spinbox'].value()
        self.sigScannerSettingsChanged.emit({'scan_resolution': {axis: scan_res}})
        return

    @QtCore.Slot(bool)
    def toggle_cursor_zoom(self, enable):
        if self._mw.action_utility_zoom.isChecked() != enable:
            self._mw.action_utility_zoom.blockSignals(True)
            self._mw.action_utility_zoom.setChecked(enable)
            self._mw.action_utility_zoom.blockSignals(False)

        for dockwidget in self.scan_2d_dockwidgets.values():
            dockwidget.plot_widget.toggle_selection(enable)
        return

    @QtCore.Slot()
    def change_optimizer_settings(self):
        settings = dict()
        settings['settle_time'] = self._osd.init_settle_time_scienDSpinBox.value()
        settings['pixel_clock'] = self._osd.pixel_clock_frequency_scienSpinBox.value()
        settings['backscan_pts'] = self._osd.backscan_points_spinBox.value()
        settings['sequence'] = [s.strip() for s in
                                self._osd.optimization_sequence_lineEdit.text().split(',')]
        axes_dict = dict()
        for axis, widget_dict in self.optimizer_settings_axes_widgets.items():
            axes_dict[axis] = dict()
            axes_dict[axis]['range'] = widget_dict['range_spinbox'].value()
            axes_dict[axis]['resolution'] = widget_dict['res_spinbox'].value()
        settings['axes'] = axes_dict
        self.sigOptimizerSettingsChanged.emit(settings)
        return

    @QtCore.Slot()
    @QtCore.Slot(dict)
    def update_optimizer_settings(self, settings=None):
        if not isinstance(settings, dict):
            settings = self.scanninglogic().optimizer_settings

        if 'settle_time' in settings:
            self._osd.init_settle_time_scienDSpinBox.blockSignals(True)
            self._osd.init_settle_time_scienDSpinBox.setValue(settings['settle_time'])
            self._osd.init_settle_time_scienDSpinBox.blockSignals(False)
        if 'pixel_clock' in settings:
            self._osd.pixel_clock_frequency_scienSpinBox.blockSignals(True)
            self._osd.pixel_clock_frequency_scienSpinBox.setValue(settings['pixel_clock'])
            self._osd.pixel_clock_frequency_scienSpinBox.blockSignals(False)
        if 'backscan_pts' in settings:
            self._osd.backscan_points_spinBox.blockSignals(True)
            self._osd.backscan_points_spinBox.setValue(settings['backscan_pts'])
            self._osd.backscan_points_spinBox.blockSignals(False)
        if 'axes' in settings:
            for axis, axis_dict in settings['axes'].items():
                if 'range' in axis_dict:
                    spinbox = self.optimizer_settings_axes_widgets[axis]['range_spinbox']
                    spinbox.blockSignals(True)
                    spinbox.setValue(axis_dict['range'])
                    spinbox.blockSignals(False)
                if 'resolution' in axis_dict:
                    spinbox = self.optimizer_settings_axes_widgets[axis]['res_spinbox']
                    spinbox.blockSignals(True)
                    spinbox.setValue(axis_dict['resolution'])
                    spinbox.blockSignals(False)
            # Adjust crosshair size according to optimizer range
            for scan_axes, dockwidget in self.scan_2d_dockwidgets.items():
                if scan_axes[0] not in settings['axes'] and scan_axes[1] not in settings['axes']:
                    continue
                crosshair = dockwidget.plot_widget.crosshairs[0]
                if scan_axes[0] in settings['axes'] and 'range' in settings['axes'][scan_axes[0]]:
                    x_size = settings['axes'][scan_axes[0]]['range']
                else:
                    x_size = crosshair.size[0]
                if scan_axes[1] in settings['axes'] and 'range' in settings['axes'][scan_axes[1]]:
                    y_size = settings['axes'][scan_axes[1]]['range']
                else:
                    y_size = crosshair.size[1]
                crosshair.set_size((x_size, y_size))
        if 'sequence' in settings:
            self._osd.optimization_sequence_lineEdit.blockSignals(True)
            self._osd.optimization_sequence_lineEdit.setText(','.join(settings['sequence']))
            self._osd.optimization_sequence_lineEdit.blockSignals(False)
            constraints = self.scanninglogic().scanner_constraints
            for seq_step in settings['sequence']:
                is_1d_step = False
                for axis, axis_constr in constraints.items():
                    if seq_step == axis:
                        self.optimizer_dockwidget.plot_widget.setLabel(
                            'bottom', axis, units=axis_constr['unit'])
                        self.optimizer_dockwidget.plot_item.setData(np.zeros(10))
                        is_1d_step = True
                        break
                if not is_1d_step:
                    for axis, axis_constr in constraints.items():
                        if seq_step.startswith(axis):
                            self.optimizer_dockwidget.scan_widget.setLabel(
                                'bottom', axis, units=axis_constr['unit'])
                            second_axis = seq_step.split(axis, 1)[-1]
                            self.optimizer_dockwidget.scan_widget.setLabel(
                                'left', second_axis, units=constraints[second_axis]['unit'])
                            self.optimizer_dockwidget.image_item.setImage(image=np.zeros((2, 2)))
                            break
        return
