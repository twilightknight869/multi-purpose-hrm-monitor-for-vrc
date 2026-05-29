using System.Collections.Generic;
using System.Net.Http;
using System.Text.Json;
using HRMMonitor.Models;

namespace HRMMonitor.Services;

/// <summary>
/// Verifies the user's license key against the HRM license API.
/// Enforces a 6-hour daily usage limit for free (unlicensed) users.
/// Checks on startup, then every 60 minutes while the app is running.
/// </summary>
public class LicenseService : IDisposable
{
    // ── Licensing config ──────────────────────────────────────────
    // Set these to your Railway/Render URL and the API_SECRET from your bot's .env
    public const string ApiUrl    = "https://your-bot.railway.app";   // <-- update after deploy
    public const string ApiSecret = "change-this-to-something-long-and-random-123456";

    // Free tier: 6 hours per day (tracked in registry as seconds used today)
    private const int FreeDailyLimitSeconds = 6 * 60 * 60;

    // ── State ─────────────────────────────────────────────────────
    private LicenseStatus _status = LicenseStatus.Unknown;
    private DateTime      _lastCheck = DateTime.MinValue;
    private System.Timers.Timer? _checkTimer;
    private System.Timers.Timer? _usageTimer;   // ticks every second for free users
    private int           _todaySeconds;        // seconds used today (free users)

    public LicenseStatus Status => _status;
    public bool IsPremium => _status == LicenseStatus.Premium;
    public bool IsBlocked => _status == LicenseStatus.FreeLimitReached;
    public int  ActiveDevSlot { get; private set; }   // 0 = not a dev key

    public event Action<LicenseStatus>? StatusChanged;
    public event Action<int>?           SecondsRemainingChanged;  // free tier countdown

    private readonly HttpClient _http = new();

    // ── Start ─────────────────────────────────────────────────────
    public void Start()
    {
        // Load today's usage from settings
        var s = AppSettings.Instance;
        var today = DateTime.Today.ToString("yyyyMMdd");
        if (s.UsageDate != today)
        {
            s.UsageDate    = today;
            s.UsageSeconds = 0;
        }
        _todaySeconds = s.UsageSeconds;

        // Always run on a background thread — the dev key path has no await
        // and would deadlock if run on the UI thread with Dispatcher.Invoke.
        _ = Task.Run(CheckAsync);

        // Recheck every 60 min
        _checkTimer = new System.Timers.Timer(60 * 60 * 1000) { AutoReset = true };
        _checkTimer.Elapsed += (_, _) => _ = CheckAsync();
        _checkTimer.Start();
    }

    public void StartUsageTracking()
    {
        if (IsPremium) return;  // premium users don't need tracking

        _usageTimer?.Dispose();
        _usageTimer = new System.Timers.Timer(1000) { AutoReset = true };
        _usageTimer.Elapsed += (_, _) =>
        {
            _todaySeconds++;
            AppSettings.Instance.UsageSeconds = _todaySeconds;

            int remaining = FreeDailyLimitSeconds - _todaySeconds;
            SecondsRemainingChanged?.Invoke(Math.Max(0, remaining));

            if (_todaySeconds >= FreeDailyLimitSeconds && _status != LicenseStatus.FreeLimitReached)
            {
                _status = LicenseStatus.FreeLimitReached;
                StatusChanged?.Invoke(_status);
            }
        };
        _usageTimer.Start();
    }

    public void StopUsageTracking()
    {
        _usageTimer?.Stop();
    }

    // ── Last dev key password prompt result ───────────────────────
    public DevKeyManager.DevKeyResult LastDevKeyResult { get; private set; }
        = DevKeyManager.DevKeyResult.NotADevKey;
    public int LastDevKeySlot { get; private set; }

    // ── License check ─────────────────────────────────────────────
    public async Task CheckAsync()
    {
        var key = AppSettings.Instance.LicenseKey.Trim();

        // No key entered → free tier
        if (string.IsNullOrEmpty(key))
        {
            SetStatus(LicenseStatus.Free);
            return;
        }

        // ── Dev key path (no network, password + optional HWID) ───
        var devResult = DevKeyManager.Validate(key,
            AppSettings.Instance.DevPassword, out int slot);
        LastDevKeyResult = devResult;
        LastDevKeySlot   = slot;

        // Track the slot as soon as we know it's a dev key (any result)
        if (devResult != DevKeyManager.DevKeyResult.NotADevKey)
            ActiveDevSlot = slot;

        switch (devResult)
        {
            case DevKeyManager.DevKeyResult.Valid:
                SetStatus(LicenseStatus.Premium);
                _usageTimer?.Stop();
                return;

            case DevKeyManager.DevKeyResult.NotADevKey:
                break;  // fall through to API check

            case DevKeyManager.DevKeyResult.PasswordRequired:
            case DevKeyManager.DevKeyResult.PasswordWrong:
            case DevKeyManager.DevKeyResult.HwidMismatch:
            case DevKeyManager.DevKeyResult.HwidNotBound:
                SetStatus(LicenseStatus.DevKeyPending);
                return;
        }

        try
        {
            _http.DefaultRequestHeaders.Remove("x-hrm-secret");
            _http.DefaultRequestHeaders.Add("x-hrm-secret", ApiSecret);

            var url  = $"{ApiUrl.TrimEnd('/')}/verify?key={Uri.EscapeDataString(key)}";
            var json = await _http.GetStringAsync(url);

            using var doc  = JsonDocument.Parse(json);
            var valid = doc.RootElement.GetProperty("valid").GetBoolean();

            if (valid)
            {
                SetStatus(LicenseStatus.Premium);
                _usageTimer?.Stop();  // stop counting — premium has no limit
            }
            else
            {
                var reason = doc.RootElement.TryGetProperty("reason", out var r)
                    ? r.GetString() : "invalid";
                SetStatus(reason == "revoked" ? LicenseStatus.Revoked : LicenseStatus.Invalid);
            }
        }
        catch
        {
            // Network error — if we had premium before, keep it (offline grace)
            if (_status != LicenseStatus.Premium)
                SetStatus(LicenseStatus.Free);
        }

        _lastCheck = DateTime.Now;
    }

    private void SetStatus(LicenseStatus s)
    {
        if (_status == s) return;
        _status = s;
        StatusChanged?.Invoke(s);
    }

    // Called by DevKeyWindow after successful password/HWID validation
    public void SetStatus_Internal(LicenseStatus s) => SetStatus(s);

    // ── Free tier helpers ─────────────────────────────────────────
    public int SecondsRemaining =>
        Math.Max(0, FreeDailyLimitSeconds - _todaySeconds);

    public string TimeRemainingDisplay
    {
        get
        {
            var s = SecondsRemaining;
            return $"{s / 3600}h {(s % 3600) / 60}m";
        }
    }

    public static string FormatLimit() => "6 hours/day";

    public void Dispose()
    {
        _checkTimer?.Dispose();
        _usageTimer?.Dispose();
        _http.Dispose();
    }
}

public enum LicenseStatus
{
    Unknown,
    Free,
    Premium,
    Invalid,
    Revoked,
    FreeLimitReached,
    DevKeyPending,      // dev key found but needs password / HWID binding
}
