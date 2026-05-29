using System.IO;
using System.Media;
using System.Text;
using System.Windows.Threading;

namespace HRMMonitor.Services;

/// <summary>
/// Plays a synthesized "lub-dub" heartbeat sound that speeds up with BPM.
/// The WAV is generated in memory — no external audio files needed.
/// </summary>
public class HeartbeatPlayer : IDisposable
{
    private readonly SoundPlayer     _player;
    private readonly MemoryStream    _wav;
    private readonly DispatcherTimer _timer = new();
    private          bool            _enabled = true;
    private          int             _lastBpm;

    public bool Enabled
    {
        get => _enabled;
        set { _enabled = value; if (!value) _timer.Stop(); }
    }

    public HeartbeatPlayer()
    {
        _wav    = new MemoryStream(GenerateHeartbeatWav());
        _player = new SoundPlayer(_wav);
        _player.Load();

        _timer.Tick += (_, _) => PlayBeat();
    }

    public void SetBpm(int bpm)
    {
        _lastBpm = bpm;
        if (!_enabled || bpm <= 0) { _timer.Stop(); return; }

        // Interval = one beat in milliseconds
        double intervalMs = 60_000.0 / bpm;
        _timer.Interval = TimeSpan.FromMilliseconds(intervalMs);
        if (!_timer.IsEnabled) _timer.Start();
    }

    public void Stop() => _timer.Stop();

    private void PlayBeat()
    {
        if (!_enabled) return;
        try
        {
            _wav.Position = 0;
            _player.Play();
        }
        catch { /* audio device not available — ignore */ }
    }

    // ── Synthesised heartbeat WAV (PCM 44100 Hz, 16-bit mono) ────────
    private static byte[] GenerateHeartbeatWav()
    {
        const int sampleRate    = 44100;
        const int bitsPerSample = 16;
        const int channels      = 1;

        // 500 ms total — lub at 0 ms, dub at 180 ms
        int totalSamples = sampleRate / 2;
        var samples = new short[totalSamples];

        AddThump(samples, sampleRate, startSec: 0.00, durSec: 0.10, freqHz: 65.0, amp: 0.80);
        AddThump(samples, sampleRate, startSec: 0.18, durSec: 0.09, freqHz: 58.0, amp: 0.55);

        using var ms = new MemoryStream();
        using var bw = new BinaryWriter(ms);

        int dataBytes = totalSamples * (bitsPerSample / 8);
        bw.Write(Encoding.ASCII.GetBytes("RIFF"));
        bw.Write(36 + dataBytes);
        bw.Write(Encoding.ASCII.GetBytes("WAVE"));
        bw.Write(Encoding.ASCII.GetBytes("fmt "));
        bw.Write(16);
        bw.Write((short)1);                                        // PCM
        bw.Write((short)channels);
        bw.Write(sampleRate);
        bw.Write(sampleRate * channels * bitsPerSample / 8);       // byte rate
        bw.Write((short)(channels * bitsPerSample / 8));           // block align
        bw.Write((short)bitsPerSample);
        bw.Write(Encoding.ASCII.GetBytes("data"));
        bw.Write(dataBytes);
        foreach (var s in samples) bw.Write(s);

        return ms.ToArray();
    }

    /// <summary>Adds a single thump (sine + exponential decay) to the sample buffer.</summary>
    private static void AddThump(short[] buf, int rate, double startSec, double durSec,
                                  double freqHz, double amp)
    {
        int start  = (int)(startSec * rate);
        int length = (int)(durSec   * rate);
        for (int i = 0; i < length && start + i < buf.Length; i++)
        {
            double t        = (double)i / rate;
            double envelope = Math.Exp(-t * 30.0);           // sharp decay = "thump"
            double wave     = Math.Sin(2 * Math.PI * freqHz * t);
            int    value    = (int)(wave * envelope * amp * short.MaxValue);
            buf[start + i]  = (short)Math.Clamp(buf[start + i] + value, short.MinValue, short.MaxValue);
        }
    }

    public void Dispose()
    {
        _timer.Stop();
        _player.Dispose();
        _wav.Dispose();
    }
}
