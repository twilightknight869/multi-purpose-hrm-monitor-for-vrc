using Microsoft.Win32;

namespace HRMMonitor.Models;

/// <summary>
/// Persisted app settings via the Windows registry (HKCU).
/// All properties auto-save on set.
/// </summary>
public class AppSettings
{
    private const string RegPath = @"Software\HRMMonitor\v2";
    private readonly RegistryKey _key;

    public static AppSettings Instance { get; } = new();

    private AppSettings()
    {
        _key = Registry.CurrentUser.CreateSubKey(RegPath);
    }

    // ── Pulsoid ────────────────────────────────────────────────────
    public string PulsoidToken
    {
        get => Get("PulsoidToken", "");
        set => Set("PulsoidToken", value);
    }

    // ── OSC ───────────────────────────────────────────────────────
    public bool OscEnabled
    {
        get => GetBool("OscEnabled", false);
        set => Set("OscEnabled", value);
    }
    public string OscIp
    {
        get => Get("OscIp", "127.0.0.1");
        set => Set("OscIp", value);
    }
    public int OscPort
    {
        get => GetInt("OscPort", 9000);
        set => Set("OscPort", value);
    }
    public string OscHrParam
    {
        get => Get("OscHrParam", "/avatar/parameters/HR");
        set => Set("OscHrParam", value);
    }
    public string OscPctParam
    {
        get => Get("OscPctParam", "/avatar/parameters/HRPercent");
        set => Set("OscPctParam", value);
    }

    // ── Chatbox ───────────────────────────────────────────────────
    public bool ChatboxEnabled
    {
        get => GetBool("ChatboxEnabled", false);
        set => Set("ChatboxEnabled", value);
    }
    public string ChatboxTemplate
    {
        get => Get("ChatboxTemplate", "{icon} {bpm} BPM  ( {tier} )\n[{bar}]");
        set => Set("ChatboxTemplate", value);
    }
    public bool ChatboxSpotify
    {
        get => GetBool("ChatboxSpotify", false);
        set => Set("ChatboxSpotify", value);
    }

    // ── Overlay appearance ────────────────────────────────────────
    public double OverlayOpacity
    {
        get => GetDouble("OverlayOpacity", 0.92);
        set => Set("OverlayOpacity", value);
    }
    public bool ShakeEnabled
    {
        get => GetBool("ShakeEnabled", true);
        set => Set("ShakeEnabled", value);
    }
    public bool HeartbeatSoundEnabled
    {
        get => GetBool("HeartbeatSound", true);
        set => Set("HeartbeatSound", value);
    }

    // ── Sharing (host) ────────────────────────────────────────────
    public bool SharingEnabled
    {
        get => GetBool("SharingEnabled", false);
        set => Set("SharingEnabled", value);
    }
    public string RoomCode
    {
        get
        {
            var code = _key.GetValue("RoomCode") as string;
            if (string.IsNullOrEmpty(code))
            {
                code = GenerateRoomCode();
                _key.SetValue("RoomCode", code);   // save it so it stays the same
            }
            return code;
        }
        set => Set("RoomCode", value);
    }
    public string AblyApiKey
    {
        get => Get("AblyApiKey", "");
        set => Set("AblyApiKey", value);
    }

    // ── Viewer ────────────────────────────────────────────────────
    public string ViewerRoomCode
    {
        get => Get("ViewerRoomCode", "");
        set => Set("ViewerRoomCode", value);
    }

    // ── Spotify ───────────────────────────────────────────────────
    public bool SpotifyEnabled
    {
        get => GetBool("SpotifyEnabled", false);
        set => Set("SpotifyEnabled", value);
    }
    public string SpotifyClientId
    {
        get => Get("SpotifyClientId", "");
        set => Set("SpotifyClientId", value);
    }
    public string SpotifyClientSecret
    {
        get => Get("SpotifyClientSecret", "");
        set => Set("SpotifyClientSecret", value);
    }
    public string SpotifyRedirectUri
    {
        get => Get("SpotifyRedirectUri", "http://127.0.0.1:8888/callback");
        set => Set("SpotifyRedirectUri", value);
    }

    // ── Spotify OAuth tokens (persisted so re-auth isn't needed after updates) ──
    public string SpotifyAccessToken
    {
        get => Get("SpotifyAccessToken", "");
        set => Set("SpotifyAccessToken", value);
    }
    public string SpotifyRefreshToken
    {
        get => Get("SpotifyRefreshToken", "");
        set => Set("SpotifyRefreshToken", value);
    }
    public long SpotifyTokenExpiry
    {
        get => GetInt("SpotifyTokenExpiry", 0);
        set => _key.SetValue("SpotifyTokenExpiry", value.ToString());
    }

    // ── SteamVR ───────────────────────────────────────────────────
    public bool SteamVrEnabled
    {
        get => GetBool("SteamVrEnabled", false);
        set => Set("SteamVrEnabled", value);
    }

    // ── Dev key password (in-memory only — never written to registry) ──
    public string DevPassword { get; set; } = "";

    // ── Dev tag visibility toggle (devs 1-3 only) ─────────────────
    public bool ShowDevTag
    {
        get => GetBool("ShowDevTag", true);
        set => Set("ShowDevTag", value);
    }

    // ── License ───────────────────────────────────────────────────
    public string LicenseKey
    {
        get => Get("LicenseKey", "");
        set => Set("LicenseKey", value);
    }
    public string UsageDate
    {
        get => Get("UsageDate", "");
        set => Set("UsageDate", value);
    }
    public int UsageSeconds
    {
        get => GetInt("UsageSeconds", 0);
        set => Set("UsageSeconds", value);
    }

    // ── Pronoun (chatbox {pronoun} token) ────────────────────────
    public string Pronoun
    {
        get => Get("Pronoun", "My");
        set => Set("Pronoun", value);
    }

    // ── Friend HR OSC (viewer sends friend BPM to avatar param) ──
    public bool FriendHrOscEnabled
    {
        get => GetBool("FriendHrOscEnabled", false);
        set => Set("FriendHrOscEnabled", value);
    }
    public string FriendHrOscParam
    {
        get => Get("FriendHrOscParam", "/avatar/parameters/FriendHR");
        set => Set("FriendHrOscParam", value);
    }

    // ── BPM thresholds ────────────────────────────────────────────
    public int BpmHigh
    {
        get => GetInt("BpmHigh", 140);
        set => Set("BpmHigh", value);
    }
    public int BpmMed
    {
        get => GetInt("BpmMed", 100);
        set => Set("BpmMed", value);
    }

    // ── Helpers ───────────────────────────────────────────────────
    private string Get(string key, string def) =>
        _key.GetValue(key) as string ?? def;

    private bool GetBool(string key, bool def) =>
        _key.GetValue(key) is int i ? i != 0 : def;

    private int GetInt(string key, int def) =>
        _key.GetValue(key) is int i ? i : def;

    private double GetDouble(string key, double def) =>
        double.TryParse(_key.GetValue(key) as string, out var d) ? d : def;

    private void Set(string key, string value) => _key.SetValue(key, value);
    private void Set(string key, bool value)   => _key.SetValue(key, value ? 1 : 0);
    private void Set(string key, int value)    => _key.SetValue(key, value);
    private void Set(string key, double value) => _key.SetValue(key, value.ToString());

    private static string GenerateRoomCode()
    {
        const string chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
        var rng = new Random();
        return new string(Enumerable.Range(0, 6).Select(_ => chars[rng.Next(chars.Length)]).ToArray());
    }
}
