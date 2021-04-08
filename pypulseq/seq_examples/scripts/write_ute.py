"""
A very basic UTE-like sequence, without ramp-sampling, ramp-RF. Achieves TE in the range of 300-400 us
"""
from copy import copy

import numpy as np
from matplotlib import pyplot as plt

import pypulseq as pp

# ======
# SETUP
# ======
seq = pp.Sequence()  # Create a new sequence object
# Define FOV and resolution
fov = 250e-3
Nx = 256
alpha = 10  # Flip angle
slice_thickness = 3e-3  # Slice thickness
TR = 10e-3  # TR
Nr = 128  # Number of radial spokes
delta = 2 * np.pi / Nr  # AAngular increment; try golden angle pi*(3-5^0.5) or 0.5 of i
ro_duration = 2.4e-3  # Read-out time: controls RO bandwidth and T2-blurring
ro_os = 2  # Oversampling
ro_asymmetry = 0.97  # 0: Fully symmetric; 1: half-echo
minRF_to_ADC_time = 50e-6  # Defines TE together with the RO asymmetry

rf_spoiling_inc = 117  # RF spoiling increment

# Set system limits
system = pp.Opts(max_grad=28, grad_unit='mT/m', max_slew=100, slew_unit='T/m/s', rf_ringdown_time=20e-6,
                 rf_dead_time=100e-6, adc_dead_time=10e-6)

# ======
# CREATE EVENTS
# ======
# Create alpha-degree slice selection pulse and gradient
rf, gz, gz_reph = pp.make_sinc_pulse(flip_angle=alpha * np.pi / 180, duration=1e-3, slice_thickness=slice_thickness,
                                     apodization=0.5, time_bw_product=2, center_pos=1, system=system, return_gz=True)

# Align RO asymmetry to ADC samples
Nxo = np.round(ro_os * Nx)
ro_asymmetry = np.round(ro_asymmetry * Nxo / 2) / Nxo * 2

# Define other gradients and ADC events
delta_k = 1 / fov / (1 + ro_asymmetry)
ro_area = Nx * delta_k
gx = pp.make_trapezoid(channel='x', flat_area=ro_area, flat_time=ro_duration, system=system)
adc = pp.make_adc(num_samples=Nxo, duration=gx.flat_time, delay=gx.rise_time, system=system)
adc.delay = adc.delay - 0.5 * adc.dwell  # compensate for the 0.5 samples shift
gx_pre = pp.make_trapezoid(channel='x', area=-(gx.area - ro_area) / 2 - ro_area / 2 * (1 - ro_asymmetry), system=system)

# Gradient spoiling
gx_spoil = pp.make_trapezoid(channel='x', area=0.2 * Nx * delta_k, system=system)

# Calculate timing
TE = gz.fall_time + pp.calc_duration(gx_pre, gz_reph) + gx.rise_time + adc.dwell * Nxo / 2 * (1 - ro_asymmetry)
delay_TR = np.ceil((TR - pp.calc_duration(gx_pre, gz_reph) - pp.calc_duration(gz) - pp.calc_duration(
    gx)) / seq.grad_raster_time) * seq.grad_raster_time
assert np.all(delay_TR >= pp.calc_duration(gx_spoil))

print(f'TE = {TE * 1e6:.0f} us')

if pp.calc_duration(gz_reph) > pp.calc_duration(gx_pre):
    gx_pre.delay = pp.calc_duration(gz_reph) - pp.calc_duration(gx_pre)

rf_phase = 0
rf_inc = 0

# ======
# CONSTRUCT SEQUENCE
# ======
for i in range(Nr):
    for c in range(2):
        rf.phase_offset = rf_phase / 180 * np.pi
        adc.phase_offset = rf_phase / 180 * np.pi
        rf_inc = np.mod(rf_inc + rf_spoiling_inc, 360.0)
        rf_phase = np.mod(rf_phase + rf_inc, 360.0)

        gz.amplitude = -gz.amplitude  # Alternate GZ amplitude
        gz_reph.amplitude = -gz_reph.amplitude

        seq.add_block(rf, gz)
        phi = delta * i

        gpc = copy(gx_pre)
        gps = copy(gx_pre)
        gpc.amplitude = gx_pre.amplitude * np.cos(phi)
        gps.amplitude = gx_pre.amplitude * np.sin(phi)
        gps.channel = 'y'

        grc = copy(gx)
        grs = copy(gx)
        grc.amplitude = gx.amplitude * np.cos(phi)
        grs.amplitude = gx.amplitude * np.sin(phi)
        grs.channel = 'y'

        gsc = copy(gx_spoil)
        gss = copy(gx_spoil)
        gsc.amplitude = gx_spoil.amplitude * np.cos(phi)
        gss.amplitude = gx_spoil.amplitude * np.sin(phi)
        gss.channel = 'y'

        seq.add_block(gpc, gps, gz_reph)
        seq.add_block(grc, grs, adc)
        seq.add_block(gsc, gss, pp.make_delay(delay_TR))

# ======
# VISUALIZATION
# ======
seq.plot()

# Plot gradients to check for gaps and optimality of the timing
gw = seq.gradient_waveforms()
plt.plot(gw.T)  # Plot the entire gradient shape

# Trajectory calculation
ktraj_adc, ktraj, t_excitation, t_refocusing, t_adc = seq.calculate_kspace()

# Plot k-spaces
time_axis = np.arange(ktraj.shape[1]) * seq.grad_raster_time
plt.figure()
plt.plot(time_axis, ktraj.T)  # Plot the entire k-space trajectory
plt.plot(t_adc, ktraj_adc[0], '.')  # Sampling points on the kx-axis
plt.figure()
plt.plot(ktraj[0], ktraj[1], 'b')  # 2D plot
plt.axis('equal')  # Enforce aspect ratio for the correct trajectory display
plt.plot(ktraj_adc[0], ktraj_adc[1], 'r.')  # Plot the sampling points

plt.show()

seq.set_definition('FOV', [fov, fov, slice_thickness])
seq.set_definition('Name', 'UTE')

seq.write('ute_pypulseq.seq')
