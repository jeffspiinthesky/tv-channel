#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: DVB-T TX (2K, QPSK, CR1/2, GI1/4)
# Description: DVB-T transmit, 2K/QPSK/CR1-2/GI1-4, fed from a local UDP relay (see relay-to-hackrf.sh) instead of a file, driving a HackRF via SoapySDR.
# GNU Radio version: 3.10.12.0

from gnuradio import digital
from gnuradio import dtv
from gnuradio import gr
from gnuradio.filter import firdes
from gnuradio.fft import window
import sys
import signal
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
from gnuradio import network
import osmosdr
import time
import threading




class dvbt_tx_2k_qpsk_8mhz_test(gr.top_block):

    def __init__(self):
        gr.top_block.__init__(self, "DVB-T TX (2K, QPSK, CR1/2, GI1/4)", catch_exceptions=True)
        self.flowgraph_started = threading.Event()

        ##################################################
        # Variables
        ##################################################
        self.udp_port = udp_port = 6000
        self.tx_gain = tx_gain = 40
        self.samp_rate = samp_rate = (8000000.0 * 8) / 7
        self.center_freq = center_freq = 610e6

        ##################################################
        # Blocks
        ##################################################

        self.osmosdr_sink_0 = osmosdr.sink(
            args="numchan=" + str(1) + " " + ""
        )
        self.osmosdr_sink_0.set_sample_rate(samp_rate)
        self.osmosdr_sink_0.set_center_freq(center_freq, 0)
        self.osmosdr_sink_0.set_freq_corr(0, 0)
        self.osmosdr_sink_0.set_gain(tx_gain, 0)
        self.osmosdr_sink_0.set_if_gain(20, 0)
        self.osmosdr_sink_0.set_bb_gain(20, 0)
        self.osmosdr_sink_0.set_antenna('', 0)
        self.osmosdr_sink_0.set_bandwidth(8000000, 0)
        self.osmosdr_sink_0.set_processor_affinity([3])
        # Must match relay_to_hackrf.py's PACKETS_PER_DATAGRAM*188 -- see that
        # file's comment for why 8MHz needs a much bigger batch than 1316.
        self.network_udp_source_0 = network.udp_source(gr.sizeof_char, 1, udp_port, 0, 7520, True, False, False)
        self.dtv_dvbt_symbol_inner_interleaver_0 = dtv.dvbt_symbol_inner_interleaver(1512, dtv.T2k, 1)
        self.dtv_dvbt_reference_signals_0 = dtv.dvbt_reference_signals(
            gr.sizeof_gr_complex,
            1512,
            2048,
            dtv.MOD_QPSK,
            dtv.NH,
            dtv.C1_2,
            dtv.C1_2,
            dtv.GI_1_4,
            dtv.T2k,
            1,
            0)
        self.dtv_dvbt_reed_solomon_enc_0 = dtv.dvbt_reed_solomon_enc(2, 8, 0x11d, 255, 239, 8, 51, 8)
        self.dtv_dvbt_map_0 = dtv.dvbt_map(1512, dtv.MOD_QPSK, dtv.NH, dtv.T2k, 1)
        self.dtv_dvbt_inner_coder_0 = dtv.dvbt_inner_coder(1, 1512, dtv.MOD_QPSK, dtv.NH, dtv.C1_2)
        self.dtv_dvbt_energy_dispersal_0 = dtv.dvbt_energy_dispersal(1)
        self.dtv_dvbt_convolutional_interleaver_0 = dtv.dvbt_convolutional_interleaver(136, 12, 17)
        self.dtv_dvbt_bit_inner_interleaver_0 = dtv.dvbt_bit_inner_interleaver(1512, dtv.MOD_QPSK, dtv.NH, dtv.T2k)
        self.digital_ofdm_cyclic_prefixer_0 = digital.ofdm_cyclic_prefixer(
            2048,
            2048 + 512,
            0,
            '')
        self.digital_ofdm_cyclic_prefixer_0.set_max_output_buffer(1000000)


        ##################################################
        # Connections
        ##################################################
        self.connect((self.digital_ofdm_cyclic_prefixer_0, 0), (self.osmosdr_sink_0, 0))
        self.connect((self.dtv_dvbt_bit_inner_interleaver_0, 0), (self.dtv_dvbt_symbol_inner_interleaver_0, 0))
        self.connect((self.dtv_dvbt_convolutional_interleaver_0, 0), (self.dtv_dvbt_inner_coder_0, 0))
        self.connect((self.dtv_dvbt_energy_dispersal_0, 0), (self.dtv_dvbt_reed_solomon_enc_0, 0))
        self.connect((self.dtv_dvbt_inner_coder_0, 0), (self.dtv_dvbt_bit_inner_interleaver_0, 0))
        self.connect((self.dtv_dvbt_map_0, 0), (self.dtv_dvbt_reference_signals_0, 0))
        self.connect((self.dtv_dvbt_reed_solomon_enc_0, 0), (self.dtv_dvbt_convolutional_interleaver_0, 0))
        self.connect((self.dtv_dvbt_reference_signals_0, 0), (self.digital_ofdm_cyclic_prefixer_0, 0))
        self.connect((self.dtv_dvbt_symbol_inner_interleaver_0, 0), (self.dtv_dvbt_map_0, 0))
        self.connect((self.network_udp_source_0, 0), (self.dtv_dvbt_energy_dispersal_0, 0))


    def get_udp_port(self):
        return self.udp_port

    def set_udp_port(self, udp_port):
        self.udp_port = udp_port

    def get_tx_gain(self):
        return self.tx_gain

    def set_tx_gain(self, tx_gain):
        self.tx_gain = tx_gain
        self.osmosdr_sink_0.set_gain(self.tx_gain, 0)

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.osmosdr_sink_0.set_sample_rate(self.samp_rate)

    def get_center_freq(self):
        return self.center_freq

    def set_center_freq(self, center_freq):
        self.center_freq = center_freq
        self.osmosdr_sink_0.set_center_freq(self.center_freq, 0)




def main(top_block_cls=dvbt_tx_2k_qpsk_8mhz_test, options=None):
    if gr.enable_realtime_scheduling() != gr.RT_OK:
        gr.logger("realtime").warn("Error: failed to enable real-time scheduling.")
    tb = top_block_cls()

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    tb.start()
    tb.flowgraph_started.set()

    tb.wait()


if __name__ == '__main__':
    main()
