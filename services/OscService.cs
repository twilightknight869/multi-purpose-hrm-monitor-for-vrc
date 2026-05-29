using System.Net.Sockets;
using System.Text;

namespace HRMMonitor.Services;

/// <summary>
/// Sends BPM data to VRChat via OSC (avatar parameters + chatbox).
/// Uses raw UDP — no third-party OSC library required.
/// </summary>
public class OscService : IDisposable
{
    private UdpClient? _udp;
    private string     _ip   = "127.0.0.1";
    private int        _port = 9000;

    // Chatbox rate-limit: VRChat enforces ~3 s between messages
    private DateTime _lastChatbox = DateTime.MinValue;
    private const double ChatboxIntervalSec = 2.5;

    // ── Target management ─────────────────────────────────────────
    public void UpdateTarget(string ip, int port) => Configure(ip, port);

    public void Configure(string ip, int port)
    {
        if (_ip == ip && _port == port && _udp != null) return;
        _udp?.Dispose();
        _ip   = ip;
        _port = port;
        _udp  = new UdpClient();
        _udp.Connect(ip, port);
    }

    private void EnsureConnected()
    {
        if (_udp == null) Configure(_ip, _port);
    }

    // ── Public send methods ───────────────────────────────────────
    public void SendBpm(int bpm, string hrParam, string pctParam, int maxBpm = 255)
    {
        EnsureConnected();
        try
        {
            Send(OscFloat(hrParam,  (float)bpm));
            Send(OscFloat(pctParam, (float)Math.Clamp(bpm / (double)maxBpm, 0.0, 1.0)));
        }
        catch { /* network error — ignore */ }
    }

    public void SendChatbox(string text, bool forceNow = false)
    {
        EnsureConnected();
        if (!forceNow && (DateTime.Now - _lastChatbox).TotalSeconds < ChatboxIntervalSec)
            return;
        try
        {
            // /chatbox/input  ,sTF  (string, bool true, bool false)
            Send(OscChatbox(text));
            _lastChatbox = DateTime.Now;
        }
        catch { /* network error — ignore */ }
    }

    private void Send(byte[] packet) => _udp?.Send(packet, packet.Length);

    // ── OSC packet builders ───────────────────────────────────────

    /// <summary>OSC message with one float argument.</summary>
    private static byte[] OscFloat(string address, float value)
    {
        var buf = new List<byte>();
        buf.AddRange(OscString(address));
        buf.AddRange(OscString(",f"));
        buf.AddRange(OscFloatBytes(value));
        return buf.ToArray();
    }

    /// <summary>/chatbox/input with (string, true, false) — T/F have no data bytes.</summary>
    private static byte[] OscChatbox(string text)
    {
        var buf = new List<byte>();
        buf.AddRange(OscString("/chatbox/input"));
        buf.AddRange(OscString(",sTF"));
        buf.AddRange(OscString(text));
        return buf.ToArray();
    }

    // ── OSC encoding primitives ───────────────────────────────────

    /// <summary>Null-terminated string padded to the next multiple of 4 bytes.</summary>
    private static byte[] OscString(string s)
    {
        var raw    = Encoding.ASCII.GetBytes(s);
        int padded = ((raw.Length + 4) / 4) * 4;
        var result = new byte[padded];
        Array.Copy(raw, result, raw.Length);
        return result;
    }

    /// <summary>Big-endian 32-bit float.</summary>
    private static byte[] OscFloatBytes(float value)
    {
        var bytes = BitConverter.GetBytes(value);
        if (BitConverter.IsLittleEndian) Array.Reverse(bytes);
        return bytes;
    }

    public void Dispose()
    {
        _udp?.Dispose();
        _udp = null;
    }
}
