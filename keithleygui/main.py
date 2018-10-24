#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Tue Feb 20 15:01:18 2018

@author: SamSchott
"""

# system imports
from __future__ import division, print_function, absolute_import
import os
from visa import InvalidSession
from qtpy import QtGui, QtCore, QtWidgets, uic
from matplotlib.figure import Figure
from keithley2600 import TransistorSweepData, IVSweepData
import matplotlib as mpl
from matplotlib.backends.backend_qt5agg import (FigureCanvasQTAgg
                                                as FigureCanvas)

# local imports
from keithleygui.utils.led_indicator_widget import LedIndicator
from keithleygui.config.main import CONF

direct = os.path.dirname(os.path.realpath(__file__))
STYLE_PATH = os.path.join(direct, 'figure_style.mplstyle')


class KeithleyGuiApp(QtWidgets.QMainWindow):
    """ Provides a GUI for transfer and output sweeps on the Keithley 2600."""
    def __init__(self, keithley):
        super(self.__class__, self).__init__()
        # load user interface layout from .ui file
        uic.loadUi(os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                'main.ui'), self)
        self.keithley = keithley
        self.smu_list = list(self.keithley.SMU_LIST)

        self._set_up_tabs()  # create Keithley settings tabs
        self._set_up_fig()  # create figure area

        # create LED indicator
        self.led = LedIndicator(self)
        self.led.setDisabled(True)  # Make the led non clickable
        self.statusBar.addPermanentWidget(self.led)
        self.led.setChecked(False)

        # change style of status bar
        self.statusBar.setStyleSheet(
                'QStatusBar{background:transparent}; ' +
                'QStatusBar::item {border: 0px solid black };')

        self.setup_input_validators()  # set validators for lineEdit fields
        self.connect_ui_callbacks()  # connect to callbacks
        self._on_load_default()  # load default settings into GUI
        self.actionSaveSweepData.setEnabled(False)  # disable save menu

        # update when keithley is connected
        self._update_gui_connection()

        # create address dialog
        self.addressDialog = KeithleyAddressDialog(self.keithley)

        # connection update timer: check periodically if keithley is connected
        # and busy, act accordingly
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._check_connection)
        self.timer.start(10000)  # Call every 10 seconds

    def _string_to_Vd(self, string):
        try:
            return float(string)
        except ValueError:
            if 'trailing' in string:
                return 'trailing'
            else:
                raise ValueError('Invalid drain voltage.')

# =============================================================================
# GUI setup
# =============================================================================

    def _set_up_fig(self):

        # get figure frame to match window color, may differ between operating
        # systems, installs, etc.
        color = QtGui.QPalette().window().color().getRgb()
        color = [x/255 for x in color]

        # set up figure itself
        with mpl.style.context(['default', STYLE_PATH]):
            self.fig = Figure(facecolor=color)
            self.fig.set_tight_layout('tight')
            self.ax = self.fig.add_subplot(111)

        self.ax.set_title('Sweep data', fontsize=10)
        self.ax.set_xlabel('Voltage [V]', fontsize=9)
        self.ax.set_ylabel('Current [A]', fontsize=9)

        # This needs to be done programatically: it is impossible to specify
        # different labelcolors and tickcolors in a .mplstyle file
        self.ax.tick_params(axis='both', which='major', direction='out',
                            labelcolor='black', color=[0.5, 0.5, 0.5, 1],
                            labelsize=9)

        self.canvas = FigureCanvas(self.fig)

        height = self.frameGeometry().height() * 0.9
        self.canvas.setMinimumWidth(height)
        self.canvas.draw()

        self.gridLayout2.addWidget(self.canvas)

    def _set_up_tabs(self):
        """Create a settings tab for every SMU."""

        # get number of SMUs, create tab and grid tayout lists
        self.ntabs = len(self.smu_list)
        self.tabs = [None]*self.ntabs
        self.gridLayouts = [None]*self.ntabs

        self.labelsCbx = [None]*self.ntabs
        self.comboBoxes = [None]*self.ntabs

        self.labelsLimitI = [None]*self.ntabs
        self.lineEditsLimitI = [None]*self.ntabs
        self.labelsUnitI = [None]*self.ntabs

        self.labelsLimitV = [None]*self.ntabs
        self.lineEditsLimitV = [None]*self.ntabs
        self.labelsUnitV = [None]*self.ntabs

        # create a tab with combobox and lineEdits for each SMU
        # the tab number i corresonds to the SMU number
        for i in range(0, self.ntabs):
            self.tabs[i] = QtWidgets.QWidget()
            self.tabs[i].setObjectName('tab_%s' % str(i))
            self.tabWidgetSettings.addTab(self.tabs[i], self.smu_list[i])

            self.gridLayouts[i] = QtWidgets.QGridLayout(self.tabs[i])
            # self.gridLayouts[i].setContentsMargins(0, 0, 0, 0)
            self.gridLayouts[i].setObjectName('gridLayout_%s' % str(i))

            self.labelsCbx[i] = QtWidgets.QLabel(self.tabs[i])
            self.labelsCbx[i].setObjectName('labelsCbx_%s' % str(i))
            self.labelsCbx[i].setAlignment(QtCore.Qt.AlignRight)
            self.labelsCbx[i].setText('Sense type:')
            self.gridLayouts[i].addWidget(self.labelsCbx[i], 0, 0, 1, 1)

            self.comboBoxes[i] = QtWidgets.QComboBox(self.tabs[i])
            self.comboBoxes[i].setObjectName('comboBox_%s' % str(i))
            self.comboBoxes[i].setMinimumWidth(150);
            self.comboBoxes[i].setMaximumWidth(150);
            self.comboBoxes[i].addItems(['local (2-wire)', 'remote (4-wire)'])
            if CONF.get(self.smu_list[i], 'sense') is 'SENSE_LOCAL':
                self.comboBoxes[i].setCurrentIndex(0)
            elif CONF.get(self.smu_list[i], 'sense') is 'SENSE_REMOTE':
                self.comboBoxes[i].setCurrentIndex(1)
            self.gridLayouts[i].addWidget(self.comboBoxes[i], 0, 1, 1, 2)

            self.labelsLimitI[i] = QtWidgets.QLabel(self.tabs[i])
            self.labelsLimitI[i].setObjectName('labelLimitI_%s' % str(i))
            self.labelsLimitI[i].setAlignment(QtCore.Qt.AlignRight)
            self.labelsLimitI[i].setText('Current limit:')
            self.gridLayouts[i].addWidget(self.labelsLimitI[i], 1, 0, 1, 1)

            self.lineEditsLimitI[i] = QtWidgets.QLineEdit(self.tabs[i])
            self.lineEditsLimitI[i].setObjectName('lineEditLimitI_%s' % str(i))
            self.lineEditsLimitI[i].setMinimumWidth(50);
            self.lineEditsLimitI[i].setMaximumWidth(50);
            self.lineEditsLimitI[i].setAlignment(QtCore.Qt.AlignRight)
            self.lineEditsLimitI[i].setText(str(CONF.get(self.smu_list[i], 'limiti')))
            self.gridLayouts[i].addWidget(self.lineEditsLimitI[i], 1, 1, 1, 1)

            self.labelsUnitI[i] = QtWidgets.QLabel(self.tabs[i])
            self.labelsUnitI[i].setObjectName('labelUnitI_%s' % str(i))
            self.labelsUnitI[i].setText('A')
            self.gridLayouts[i].addWidget(self.labelsUnitI[i], 1, 2, 1, 1)

            self.labelsLimitV[i] = QtWidgets.QLabel(self.tabs[i])
            self.labelsLimitV[i].setObjectName('labelLimitV_%s' % str(i))
            self.labelsLimitV[i].setAlignment(QtCore.Qt.AlignRight)
            self.labelsLimitV[i].setText('Voltage limit:')
            self.gridLayouts[i].addWidget(self.labelsLimitV[i], 2, 0, 1, 1)

            self.lineEditsLimitV[i] = QtWidgets.QLineEdit(self.tabs[i])
            self.lineEditsLimitV[i].setObjectName('lineEditLimitV_%s' % str(i))
            self.lineEditsLimitV[i].setMinimumWidth(50);
            self.lineEditsLimitV[i].setMaximumWidth(50);
            self.lineEditsLimitV[i].setAlignment(QtCore.Qt.AlignRight)
            self.lineEditsLimitV[i].setText(str(CONF.get(self.smu_list[i], 'limitv')))
            self.gridLayouts[i].addWidget(self.lineEditsLimitV[i], 2, 1, 1, 1)

            self.labelsUnitV[i] = QtWidgets.QLabel(self.tabs[i])
            self.labelsUnitV[i].setObjectName('labelUnitV_%s' % str(i))
            self.labelsUnitV[i].setText('V')
            self.gridLayouts[i].addWidget(self.labelsUnitV[i], 2, 2, 1, 1)

    def setup_input_validators(self):
        """Set QDoubleValidators for lineEdit fields."""
        self.lineEditVgStart.setValidator(QtGui.QDoubleValidator())
        self.lineEditVgStop.setValidator(QtGui.QDoubleValidator())
        self.lineEditVgStep.setValidator(QtGui.QDoubleValidator())

        self.lineEditVdStart.setValidator(QtGui.QDoubleValidator())
        self.lineEditVdStop.setValidator(QtGui.QDoubleValidator())
        self.lineEditVdStep.setValidator(QtGui.QDoubleValidator())

        self.lineEditVStart.setValidator(QtGui.QDoubleValidator())
        self.lineEditVStop.setValidator(QtGui.QDoubleValidator())
        self.lineEditVStep.setValidator(QtGui.QDoubleValidator())

        self.lineEditInt.setValidator(QtGui.QDoubleValidator())
        self.lineEditSettling.setValidator(QtGui.QDoubleValidator())

    def connect_ui_callbacks(self):
        """Connect buttons and menues to callbacks."""
        self.pushButtonTransfer.clicked.connect(self._on_sweep_clicked)
        self.pushButtonOutput.clicked.connect(self._on_sweep_clicked)
        self.pushButtonIV.clicked.connect(self._on_sweep_clicked)
        self.pushButtonAbort.clicked.connect(self._on_abort_clicked)

        self.comboBoxGateSMU.currentIndexChanged.connect(self._on_smu_gate_changed)
        self.comboBoxDrainSMU.currentIndexChanged.connect(self._on_smu_drain_changed)

        self.actionSettings.triggered.connect(self._on_settings_clicked)
        self.actionConnect.triggered.connect(self._on_connect_clicked)
        self.actionDisconnect.triggered.connect(self._on_disconnect_clicked)
        self.action_Exit.triggered.connect(self._on_exit_clicked)
        self.actionSaveSweepData.triggered.connect(self._on_save_clicked)
        self.actionLoad_data_from_file.triggered.connect(self._on_load_clicked)
        self.actionSaveDefaults.triggered.connect(self._on_save_default)
        self.actionLoadDefaults.triggered.connect(self._on_load_default)

# =============================================================================
# Keithley status
# =============================================================================

    @QtCore.Slot()
    def _check_connection(self):
        # disconncet if keithley does not respond, test by querying model
        if self.keithley.connected and not self.keithley.busy:
            try:
                self.keithley.localnode.model
            except (InvalidSession, OSError):
                self.keithley.disconnect()
                self._update_gui_connection()

    def _check_if_busy(self):
        if self.keithley.busy:
            msg = ('Keithley is currently used by antoher program. ' +
                   'Please try again later.')
            QtWidgets.QMessageBox.information(None, str('error'), msg)

# =============================================================================
# Measurement callbacks
# =============================================================================

    def apply_smu_settings(self):
        """
        Applies SMU settings to Keithley before a measurement.
        Warning: self.keithley.reset() will reset those settings.
        """
        for i in range(0, self.ntabs):

            smu = getattr(self.keithley, self.smu_list[i])

            if self.comboBoxes[i].currentIndex() == 0:
                smu.sense = smu.SENSE_LOCAL
            elif self.comboBoxes[i].currentIndex() == 1:
                smu.sense = smu.SENSE_REMOTE

            lim_i = float(self.lineEditsLimitI[i].text())
            smu.source.limiti = lim_i
            smu.trigger.source.limiti = lim_i

            lim_v = float(self.lineEditsLimitV[i].text())
            smu.source.limitv = lim_v
            smu.trigger.source.limitv = lim_v

    @QtCore.Slot()
    def _on_sweep_clicked(self):
        """ Start a transfer measurement with current settings."""
        self._check_if_busy()
        self.apply_smu_settings()

        if self.sender() == self.pushButtonTransfer:
            self.statusBar.showMessage('    Recording transfer curve.')
            # get sweep settings
            params = {'Measurement': 'transfer'}
            params['VgStart'] = float(self.lineEditVgStart.text())
            params['VgStop'] = float(self.lineEditVgStop.text())
            params['VgStep'] = float(self.lineEditVgStep.text())
            VdListString = self.lineEditVdList.text()
            VdStringList = VdListString.split(',')
            params['VdList'] = [self._string_to_Vd(x) for x in VdStringList]

        elif self.sender() == self.pushButtonOutput:
            self.statusBar.showMessage('    Recording output curve.')
            # get sweep settings
            params = {'Measurement': 'output'}
            params['VdStart'] = float(self.lineEditVdStart.text())
            params['VdStop'] = float(self.lineEditVdStop.text())
            params['VdStep'] = float(self.lineEditVdStep.text())
            VgListString = self.lineEditVgList.text()
            VgStringList = VgListString.split(',')
            params['VgList'] = [float(x) for x in VgStringList]

        elif self.sender() == self.pushButtonIV:
            self.statusBar.showMessage('    Recording IV curve.')
            # get sweep settings
            params = {'Measurement': 'iv'}
            params['VStart'] = float(self.lineEditVStart.text())
            params['VStop'] = float(self.lineEditVStop.text())
            params['VStep'] = float(self.lineEditVStep.text())
            params['VFix'] = 0

            smusweep = self.comboBoxSweepSMU.currentText()
            other = [s for s in self.smu_list if s is not smusweep]

            params['smu_sweep'] = getattr(self.keithley, smusweep)
            params['smu_fix'] = getattr(self.keithley, other[0])

        # get aquisition settings
        params['tInt'] = float(self.lineEditInt.text())  # integration time
        params['delay'] = float(self.lineEditSettling.text())  # stabilization

        smugate = self.comboBoxGateSMU.currentText()  # gate SMU
        params['smu_gate'] = getattr(self.keithley, smugate)
        smudrain = self.comboBoxDrainSMU.currentText()
        params['smu_drain'] = getattr(self.keithley, smudrain)  # drain SMU

        if self.comboBoxSweepType.currentIndex() == 0:
            params['pulsed'] = False
        elif self.comboBoxSweepType.currentIndex() == 1:
            params['pulsed'] = True

        # create measurement thread with params dictionary
        self.measureThread = MeasureThread(self.keithley, params)
        self.measureThread.finishedSig.connect(self._on_measure_done)

        # run measurement
        self._gui_state_busy()
        self.measureThread.start()

    def _on_measure_done(self, sd):
        self.statusBar.showMessage('    Ready.')
        self._gui_state_idle()
        self.actionSaveSweepData.setEnabled(True)

        self.sweepData = sd
        self.plot_new_data()
        if not self.keithley.abort_event.is_set():
            self._on_save_clicked()

    @QtCore.Slot()
    def _on_abort_clicked(self):
        """
        Aborts current measurement.
        """
        self.keithley.abort_event.set()

# =============================================================================
# Interface callbacks
# =============================================================================

    @QtCore.Slot(int)
    def _on_smu_gate_changed(self, intSMU):
        """ Triggered when the user selects a different gate SMU. """

        if intSMU == 0 and len(self.smu_list) < 3:
            self.comboBoxDrainSMU.setCurrentIndex(1)
        elif intSMU == 1 and len(self.smu_list) < 3:
            self.comboBoxDrainSMU.setCurrentIndex(0)

    @QtCore.Slot(int)
    def _on_smu_drain_changed(self, intSMU):
        """ Triggered when the user selects a different drain SMU. """

        if intSMU == 0 and len(self.smu_list) < 3:
            self.comboBoxGateSMU.setCurrentIndex(1)
        elif intSMU == 1 and len(self.smu_list) < 3:
            self.comboBoxGateSMU.setCurrentIndex(0)

    @QtCore.Slot()
    def _on_connect_clicked(self):
        self.keithley.connect()
        self._update_gui_connection()
        if not self.keithley.connected:
            msg = ('Keithley cannot be reached at %s. ' % self.keithley.visa_address
                   + 'Please check if address is correct and Keithley is ' +
                   'turned on.')
            QtWidgets.QMessageBox.information(None, str('error'), msg)

    @QtCore.Slot()
    def _on_disconnect_clicked(self):
        self.keithley.disconnect()
        self._update_gui_connection()
        self.statusBar.showMessage('    No Keithley connected.')

    @QtCore.Slot()
    def _on_settings_clicked(self):
        self.addressDialog.show()

    @QtCore.Slot()
    def _on_save_clicked(self):
        """Show GUI to save current sweep data as text file."""
        prompt = 'Save as .txt file.'
        filename = 'untitled.txt'
        formats = 'Text file (*.txt)'
        filepath = QtWidgets.QFileDialog.getSaveFileName(self, prompt,
                                                         filename, formats)
        if len(filepath[0]) < 4:
            return
        self.sweepData.save(filepath[0])

    @QtCore.Slot()
    def _on_load_clicked(self):
        """Show GUI to load sweep data from file."""
        prompt = 'Please select a data file.'
        filepath = QtWidgets.QFileDialog.getOpenFileName(self, prompt)
        if not os.path.isfile(filepath[0]):
            return
        try:
            self.sweepData = TransistorSweepData()
            self.sweepData.load(filepath[0])
        except RuntimeError:
            self.sweepData = IVSweepData()
            self.sweepData.load(filepath[0])

        self.plot_new_data()
        self.actionSaveSweepData.setEnabled(True)

    @QtCore.Slot()
    def _on_save_default(self):
        """Saves current settings from GUI as defaults."""

        # save transfer settings
        CONF.set('Sweep', 'VgStart', float(self.lineEditVgStart.text()))
        CONF.set('Sweep', 'VgStop', float(self.lineEditVgStop.text()))
        CONF.set('Sweep', 'VgStep', float(self.lineEditVgStep.text()))

        VdListString = self.lineEditVdList.text()
        VdStringList = VdListString.split(',')
        CONF.set('Sweep', 'VdList', [self._string_to_Vd(x) for x in VdStringList])

        # save output settings
        CONF.set('Sweep', 'VdStart', float(self.lineEditVdStart.text()))
        CONF.set('Sweep', 'VdStop', float(self.lineEditVdStop.text()))
        CONF.set('Sweep', 'VdStep', float(self.lineEditVdStep.text()))

        VgListString = self.lineEditVgList.text()
        VgStringList = VgListString.split(',')
        CONF.set('Sweep', 'VgList', [float(x) for x in VgStringList])

        # save general settings
        CONF.set('Sweep', 'tInt', float(self.lineEditInt.text()))
        CONF.set('Sweep', 'delay', float(self.lineEditSettling.text()))

        # get combo box status
        if self.comboBoxSweepType.currentIndex() == 0:
            CONF.set('Sweep', 'pulsed', False)
        elif self.comboBoxSweepType.currentIndex() == 1:
            CONF.set('Sweep', 'pulsed', True)

        CONF.set('Sweep', 'gate', self.comboBoxGateSMU.currentText())
        CONF.set('Sweep', 'drain', self.comboBoxDrainSMU.currentText())

        for i in range(0, self.ntabs):

            if self.comboBoxes[i].currentIndex() == 0:
                CONF.set(self.smu_list[i], 'sense', 'SENSE_LOCAL')
            elif self.comboBoxes[i].currentIndex() == 1:
                CONF.set(self.smu_list[i], 'sense', 'SENSE_REMOTE')

            CONF.set(self.smu_list[i], 'limiti', float(self.lineEditsLimitI[i].text()))
            CONF.set(self.smu_list[i], 'limitv', float(self.lineEditsLimitV[i].text()))

    @QtCore.Slot()
    def _on_load_default(self):
        """Load default settings to interface."""

        # set text box contents
        # transfer curve settings
        self.lineEditVgStart.setText(str(CONF.get('Sweep', 'VgStart')))
        self.lineEditVgStop.setText(str(CONF.get('Sweep', 'VgStop')))
        self.lineEditVgStep.setText(str(CONF.get('Sweep', 'VgStep')))
        self.lineEditVdList.setText(str(CONF.get('Sweep', 'VdList')).strip('[]'))
        # output curve settings
        self.lineEditVdStart.setText(str(CONF.get('Sweep', 'VdStart')))
        self.lineEditVdStop.setText(str(CONF.get('Sweep', 'VdStop')))
        self.lineEditVdStep.setText(str(CONF.get('Sweep', 'VdStep')))
        self.lineEditVgList.setText(str(CONF.get('Sweep', 'VgList')).strip('[]'))

        # other
        self.lineEditInt.setText(str(CONF.get('Sweep', 'tInt')))
        self.lineEditSettling.setText(str(CONF.get('Sweep', 'delay')))

        # set PULSED comboBox status
        pulsed = CONF.get('Sweep', 'pulsed')
        if pulsed is False:
            self.comboBoxSweepType.setCurrentIndex(0)
        elif pulsed is True:
            self.comboBoxSweepType.setCurrentIndex(1)

        # Set SMU selection comboBox status
        cmbList = list(self.smu_list)  # get list of all SMUs
        # We have to comboBoxes. If there are less SMU's, extend list.
        while len(cmbList) < 2:
            cmbList.append('--')

        self.comboBoxGateSMU.clear()
        self.comboBoxDrainSMU.clear()
        self.comboBoxSweepSMU.clear()
        self.comboBoxGateSMU.addItems(cmbList)
        self.comboBoxDrainSMU.addItems(cmbList)
        self.comboBoxSweepSMU.addItems(self.smu_list)

        try:
            self.comboBoxGateSMU.setCurrentIndex(cmbList.index(CONF.get('Sweep', 'gate')))
            self.comboBoxDrainSMU.setCurrentIndex(cmbList.index(CONF.get('Sweep', 'drain')))
        except ValueError:
            self.comboBoxGateSMU.setCurrentIndex(0)
            self.comboBoxDrainSMU.setCurrentIndex(1)
            msg = 'Could not find last used SMUs in Keithley driver.'
            QtWidgets.QMessageBox.information(None, str('error'), msg)

        for i in range(0, self.ntabs):
            sense = CONF.get(self.smu_list[i], 'sense')
            if sense == 'SENSE_LOCAL':
                self.comboBoxes[i].setCurrentIndex(0)
            elif sense == 'SENSE_REMOTE':
                self.comboBoxes[i].setCurrentIndex(1)

            self.lineEditsLimitI[i].setText(str(CONF.get(self.smu_list[i], 'limiti')))
            self.lineEditsLimitV[i].setText(str(CONF.get(self.smu_list[i], 'limitv')))

    @QtCore.Slot()
    def _on_exit_clicked(self):
        self.keithley.disconnect()
        self.timer.stop()
        self.deleteLater()

# =============================================================================
# Interface states
# =============================================================================

    def _update_gui_connection(self):
        """Check if Keithley is connected and update GUI."""
        if self.keithley.connected and not self.keithley.busy:
            self._gui_state_idle()
            self.led.setChecked(True)

        elif self.keithley.connected and self.keithley.busy:
            self._gui_state_busy()
            self.led.setChecked(True)

        elif not self.keithley.connected:
            self._gui_state_disconnected()
            self.led.setChecked(False)

    def _gui_state_busy(self):
        """Set GUI to state for running measurement."""

        self.pushButtonTransfer.setEnabled(False)
        self.pushButtonOutput.setEnabled(False)
        self.pushButtonIV.setEnabled(False)
        self.pushButtonAbort.setEnabled(True)

        self.actionConnect.setEnabled(False)
        self.actionDisconnect.setEnabled(False)

        self.statusBar.showMessage('    Measuring.')

    def _gui_state_idle(self):
        """Set GUI to state for IDLE Keithley."""

        self.pushButtonTransfer.setEnabled(True)
        self.pushButtonOutput.setEnabled(True)
        self.pushButtonIV.setEnabled(True)
        self.pushButtonAbort.setEnabled(True)

        self.actionConnect.setEnabled(False)
        self.actionDisconnect.setEnabled(True)
        self.statusBar.showMessage('    Ready.')

    def _gui_state_disconnected(self):
        """Set GUI to state for disconnected Keithley."""

        self.pushButtonTransfer.setEnabled(False)
        self.pushButtonOutput.setEnabled(False)
        self.pushButtonIV.setEnabled(False)
        self.pushButtonAbort.setEnabled(False)

        self.actionConnect.setEnabled(True)
        self.actionDisconnect.setEnabled(False)
        self.statusBar.showMessage('    No Keithley connected.')

# =============================================================================
# Plotting commands
# =============================================================================

    def plot_new_data(self):
        """
        Plots the transfer or output curves.
        """
        self.ax.clear()  # clear current plot

        if self.sweepData.sweepType == 'transfer':
            for v in self.sweepData.step_list():
                self.ax.semilogy(self.sweepData.vSweep[v], abs(self.sweepData.iDrain[v]),
                                 '-', label='Drain current, Vd = %s' % v)
                self.ax.semilogy(self.sweepData.vSweep[v], abs(self.sweepData.iGate[v]),
                                 '--', label='Gate current, Vd = %s' % v)
                self.ax.legend(loc=3)

            self.ax.autoscale(axis='x', tight=True)
            self.ax.set_title('Transfer data')
            self.ax.set_xlabel('Gate voltage [V]')
            self.ax.set_ylabel('Current [A]')

            self.canvas.draw()

        elif self.sweepData.sweepType == 'output':
            for v in self.sweepData.step_list():
                self.ax.plot(self.sweepData.vSweep[v], abs(self.sweepData.iDrain[v]),
                             '-', label='Drain current, Vg = %s' % v)
                self.ax.plot(self.sweepData.vSweep[v], abs(self.sweepData.iGate[v]),
                             '--', label='Gate current, Vg = %s' % v)
                self.ax.legend()

            self.ax.autoscale(axis='x', tight=True)
            self.ax.set_title('Output data')
            self.ax.set_xlabel('Drain voltage [V]')
            self.ax.set_ylabel('Current [A]')
            self.canvas.draw()

        elif self.sweepData.sweepType == 'iv':

            self.ax.plot(self.sweepData.v, self.sweepData.i, '-', label='Current')
            self.ax.legend()

            self.ax.autoscale(axis='x', tight=True)
            self.ax.set_title('IV sweep data')
            self.ax.set_xlabel('Voltage [V]')
            self.ax.set_ylabel('Current [A]')
            self.canvas.draw()


class KeithleyAddressDialog(QtWidgets.QDialog):
    """
    Provides a user dialog to select the modules for the feed.
    """
    def __init__(self, keithley):
        super(self.__class__, self).__init__()
        # load user interface layout from .ui file
        uic.loadUi(os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                'address_dialog.ui'), self)

        self.keithley = keithley
        self.lineEditAddress.setText(self.keithley.visa_address)

        self.buttonBox.accepted.connect(self._onAccept)

    def _onAccept(self):
        # update connection settings in mercury feed
        self.keithley.visa_address = self.lineEditAddress.text()
        CONF.set('Connection', 'KEITHLEY_ADDRESS', self.keithley.visa_address)
        # reconnect to new IP address
        self.keithley.disconnect()
        self.keithley.connect()


class MeasureThread(QtCore.QThread):

    startedSig = QtCore.Signal()
    finishedSig = QtCore.Signal(object)

    def __init__(self, keithley, params):
        QtCore.QThread.__init__(self)
        self.keithley = keithley
        self.params = params

    def __del__(self):
        self.wait()

    def run(self):
        self.startedSig.emit()

        if self.params['Measurement'] == 'transfer':
            sweepData = self.keithley.transferMeasurement(
                    self.params['smu_gate'], self.params['smu_drain'], self.params['VgStart'],
                    self.params['VgStop'], self.params['VgStep'], self.params['VdList'],
                    self.params['tInt'], self.params['delay'], self.params['pulsed']
                    )
        elif self.params['Measurement'] == 'output':
            sweepData = self.keithley.outputMeasurement(
                    self.params['smu_gate'], self.params['smu_drain'], self.params['VdStart'],
                    self.params['VdStop'], self.params['VdStep'], self.params['VgList'],
                    self.params['tInt'], self.params['delay'], self.params['pulsed']
                    )

        elif self.params['Measurement'] == 'iv':
            Vsweep, Isweep, = self.voltageSweep(
                    self.params['smu_sweep'], self.params['smu_fix'], self.params['VStart'],
                    self.params['VStop'], self.params['VStep'], self.params['VFix'],
                    self.params['tInt'], self.params['delay'], self.params['pulsed']
                    )
            sweepData = IVSweepData(Vsweep, Isweep)

        self.finishedSig.emit(sweepData)


def run():

    import sys
    from keithley2600 import Keithley2600

    KEITHLEY_ADDRESS = CONF.get('Connection', 'KEITHLEY_ADDRESS')
    keithley = Keithley2600(KEITHLEY_ADDRESS)

    app = QtWidgets.QApplication(sys.argv)
    keithleyGUI = KeithleyGuiApp(keithley)
    keithleyGUI.show()

    sys.exit(app.exec_())


if __name__ == '__main__':
    run()
