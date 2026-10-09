package org.vector.probe;

import android.Manifest;
import android.content.pm.PackageManager;
import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.AudioTrack;
import android.media.MediaRecorder;
import android.os.VibrationEffect;
import android.os.Vibrator;
import java.util.Arrays;

final class AudioCollector {
    private AudioCollector() { }
    static void start(DiagnosticController c, DiagnosticJob j) {
        if (j.id.equals("vibration")) {
            Vibrator vibrator = c.activity.getSystemService(Vibrator.class);
            if (vibrator == null || !vibrator.hasVibrator()) { c.finish(j, "UNSUPPORTED", "HARDWARE_ABSENT"); return; }
            if (!c.own(j, vibrator::cancel)) return; vibrator.vibrate(VibrationEffect.createOneShot(300, VibrationEffect.DEFAULT_AMPLITUDE));
            j.metric("effect_scheduled", 1, "boolean"); c.confirm(j); return;
        }
        if (j.id.equals("speaker")) {
            short[] tone = new short[16000];
            for (int i = 0; i < tone.length; i++) tone[i] = (short) (1600 * Math.sin(2 * Math.PI * 440 * i / 16000));
            AudioTrack track = new AudioTrack.Builder()
                    .setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build())
                    .setAudioFormat(new AudioFormat.Builder().setSampleRate(16000).setEncoding(AudioFormat.ENCODING_PCM_16BIT).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
                    .setBufferSizeInBytes(tone.length * 2).setTransferMode(AudioTrack.MODE_STATIC).build();
            if (!c.own(j, () -> { try { if (track.getPlayState() == AudioTrack.PLAYSTATE_PLAYING) track.stop(); } finally { track.release(); } })) return;
            if (track.getState() != AudioTrack.STATE_INITIALIZED || track.write(tone, 0, tone.length) != tone.length) { c.finish(j, "ERROR", "INITIALIZATION_ERROR"); return; }
            Arrays.fill(tone, (short) 0); track.play(); j.metric("tone_submitted", 1, "boolean");
            c.main.postDelayed(() -> { if (c.current(j)) { track.stop(); c.confirm(j); } }, 1100); return;
        }
        if (c.activity.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) { c.finish(j, "RESTRICTED", "PERMISSION_DENIED"); return; }
        int minimum = AudioRecord.getMinBufferSize(16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
        if (minimum <= 0 || minimum > 65536) { c.finish(j, "UNSUPPORTED", "AUDIO_FORMAT_UNSUPPORTED"); return; }
        AudioRecord record = new AudioRecord(MediaRecorder.AudioSource.MIC, 16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, Math.max(8192, minimum));
        if (!c.own(j, () -> { try { if (record.getRecordingState() == AudioRecord.RECORDSTATE_RECORDING) record.stop(); } finally { record.release(); } })) return;
        if (record.getState() != AudioRecord.STATE_INITIALIZED) { c.finish(j, "ERROR", "INITIALIZATION_ERROR"); return; }
        record.startRecording();
        c.main.post(new Runnable() {
            final short[] buffer = new short[2048]; long count; double squares; int peak;
            @Override public void run() {
                if (!c.current(j)) return;
                if (c.activity.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) { c.finish(j, "RESTRICTED", "PERMISSION_DENIED"); return; }
                try {
                    int received = record.read(buffer, 0, buffer.length, AudioRecord.READ_NON_BLOCKING);
                    if (received < 0) { c.finish(j, "ERROR", "READ_ERROR"); return; }
                    int level = 0;
                    for (int i = 0; i < received; i++) { int value = Math.abs(buffer[i]); level = Math.max(level, value); squares += (double) value * value; }
                    peak = Math.max(peak, level);
                    count += received; Arrays.fill(buffer, (short) 0);
                    // No samples means no level was observed: null, never a fabricated 0.0.
                    j.metric("audio_samples", count, "count"); j.metric("audio_peak", count == 0 ? null : peak / 32768.0, "unitless");
                    j.metric("audio_rms", count == 0 ? null : Math.sqrt(squares / count) / 32768.0, "unitless");
                    if (received > 0) c.ui.inputLevel(j, (int) (level * 100L / 32768));
                    if (DiagnosticController.now() - j.started >= 3000) { record.stop(); c.confirm(j); }
                    else c.main.postDelayed(this, 40);
                } catch (SecurityException error) { c.finish(j, "RESTRICTED", "PERMISSION_DENIED"); }
                catch (IllegalStateException error) { c.finish(j, "ERROR", "READ_ERROR"); }
                finally { Arrays.fill(buffer, (short) 0); }
            }
        });
    }
}
