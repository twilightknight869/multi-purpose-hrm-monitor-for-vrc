using System.Net.Http;
using System.Text.Json;

namespace HRMMonitor.Services;

/// <summary>
/// Checks GitHub releases for a newer version.
/// Fires UpdateAvailable(downloadUrl) when one is found.
/// Checks once at startup (after 2 min) then every 15 min.
/// </summary>
public class UpdateService : IDisposable
{
    private const string Owner   = "twilightknight869";
    private const string Repo    = "Multi-Purpose-HRM-Monitor-For-VRC";
    private const string Version = "2.0.0";

    private readonly HttpClient _http = new();
    private readonly System.Timers.Timer _timer;
    private bool _checking;

    public event Action<string>? UpdateAvailable;   // download URL

    public UpdateService()
    {
        _http.DefaultRequestHeaders.UserAgent.ParseAdd($"HRMMonitor/{Version}");

        _timer = new System.Timers.Timer(15 * 60 * 1000) { AutoReset = true };
        _timer.Elapsed += (_, _) => _ = CheckAsync();
    }

    public void Start()
    {
        _timer.Start();
        // First check 2 min after launch
        _ = Task.Run(async () =>
        {
            await Task.Delay(TimeSpan.FromMinutes(2));
            await CheckAsync();
        });
    }

    private async Task CheckAsync()
    {
        if (_checking) return;
        _checking = true;
        try
        {
            var url  = $"https://api.github.com/repos/{Owner}/{Repo}/releases/latest";
            var json = await _http.GetStringAsync(url);
            using var doc    = JsonDocument.Parse(json);
            var latest = doc.RootElement.GetProperty("tag_name").GetString()?.TrimStart('v') ?? "";
            var dlUrl  = doc.RootElement.GetProperty("zipball_url").GetString() ?? "";

            if (IsNewer(latest, Version) && !string.IsNullOrEmpty(dlUrl))
                UpdateAvailable?.Invoke(dlUrl);
        }
        catch { /* no internet / API rate limit — silent */ }
        finally { _checking = false; }
    }

    private static bool IsNewer(string latest, string current)
    {
        static Version? Parse(string s) =>
            System.Version.TryParse(s, out var v) ? v : null;

        var l = Parse(latest);
        var c = Parse(current);
        return l != null && c != null && l > c;
    }

    public void Dispose()
    {
        _timer.Dispose();
        _http.Dispose();
    }
}
