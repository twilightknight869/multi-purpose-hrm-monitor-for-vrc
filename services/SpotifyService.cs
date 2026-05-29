using System.Diagnostics;
using System.IO;
using System.Net;
using System.Text;
using HRMMonitor.Models;
using SpotifyAPI.Web;

namespace HRMMonitor.Services;

public record TrackInfo(string TrackName, string ArtistName, bool IsPlaying);

/// <summary>
/// Polls Spotify every 3 s for the currently playing track.
/// Tokens are persisted in the registry so re-auth survives app updates.
/// </summary>
public class SpotifyService : IDisposable
{
    private SpotifyClient?           _spotify;
    private HttpListener?            _listener;
    private CancellationTokenSource  _cts = new();
    private TrackInfo?               _last;

    public event Action<TrackInfo?>? TrackChanged;
    public event Action<string>?     StatusChanged;

    // ── Authorization ─────────────────────────────────────────────
    public async Task AuthorizeAsync(string clientId, string clientSecret, string redirectUri)
    {
        await StopAsync();
        _cts = new CancellationTokenSource();

        var uri     = new Uri(redirectUri);
        var prefix  = $"http://{uri.Host}:{uri.Port}{uri.AbsolutePath}";
        if (!prefix.EndsWith("/")) prefix += "/";

        _listener = new HttpListener();
        _listener.Prefixes.Add(prefix);

        try { _listener.Start(); }
        catch (HttpListenerException ex)
        {
            StatusChanged?.Invoke($"error:listener {ex.Message}");
            return;
        }

        // Build login URL and open browser
        var loginReq = new LoginRequest(uri, clientId, LoginRequest.ResponseType.Code)
        {
            Scope = new[] { Scopes.UserReadCurrentlyPlaying, Scopes.UserReadPlaybackState },
        };
        Process.Start(new ProcessStartInfo(loginReq.ToUri().ToString()) { UseShellExecute = true });
        StatusChanged?.Invoke("authorizing");

        // Wait for callback (2 min timeout)
        var tcs = new TaskCompletionSource<string?>();
        _ = Task.Run(async () =>
        {
            try
            {
                var ctx  = await _listener.GetContextAsync();
                var code = ctx.Request.QueryString["code"];
                // Send a simple close-me page
                var html = Encoding.UTF8.GetBytes(
                    "<html><body><h2>HRM Monitor: authorized! You can close this tab.</h2></body></html>");
                ctx.Response.ContentType     = "text/html";
                ctx.Response.ContentLength64 = html.Length;
                await ctx.Response.OutputStream.WriteAsync(html);
                ctx.Response.Close();
                tcs.TrySetResult(code);
            }
            catch { tcs.TrySetResult(null); }
        });

        string? authCode;
        try   { authCode = await tcs.Task.WaitAsync(TimeSpan.FromMinutes(2)); }
        catch { authCode = null; }

        _listener.Stop();
        _listener = null;

        if (string.IsNullOrEmpty(authCode))
        {
            StatusChanged?.Invoke("error:auth timeout");
            return;
        }

        try
        {
            var config   = SpotifyClientConfig.CreateDefault();
            var tokenReq = new AuthorizationCodeTokenRequest(clientId, clientSecret, authCode, uri);
            var token    = await new OAuthClient(config).RequestToken(tokenReq);
            _spotify     = new SpotifyClient(token.AccessToken);

            // Persist tokens so re-auth isn't needed after updates
            AppSettings.Instance.SpotifyAccessToken  = token.AccessToken;
            AppSettings.Instance.SpotifyRefreshToken = token.RefreshToken ?? "";
            AppSettings.Instance.SpotifyTokenExpiry  = DateTimeOffset.UtcNow.AddSeconds(token.ExpiresIn).ToUnixTimeSeconds();

            StatusChanged?.Invoke("connected");
        }
        catch (Exception ex)
        {
            StatusChanged?.Invoke($"error:{ex.Message}");
        }
    }

    // ── Restore saved token (call on startup before polling) ──────
    public async Task<bool> TryRestoreAsync(string clientId, string clientSecret)
    {
        var s = AppSettings.Instance;
        if (string.IsNullOrEmpty(s.SpotifyAccessToken)) return false;

        try
        {
            // If token is expired, refresh it
            if (DateTimeOffset.UtcNow.ToUnixTimeSeconds() >= s.SpotifyTokenExpiry - 60
                && !string.IsNullOrEmpty(s.SpotifyRefreshToken))
            {
                var config      = SpotifyClientConfig.CreateDefault();
                var refreshReq  = new AuthorizationCodeRefreshRequest(clientId, clientSecret, s.SpotifyRefreshToken);
                var refreshed   = await new OAuthClient(config).RequestToken(refreshReq);
                s.SpotifyAccessToken = refreshed.AccessToken;
                s.SpotifyTokenExpiry = DateTimeOffset.UtcNow.AddSeconds(refreshed.ExpiresIn).ToUnixTimeSeconds();
                if (!string.IsNullOrEmpty(refreshed.RefreshToken))
                    s.SpotifyRefreshToken = refreshed.RefreshToken;
            }

            _spotify = new SpotifyClient(s.SpotifyAccessToken);
            StatusChanged?.Invoke("connected");
            return true;
        }
        catch
        {
            // Token invalid — clear it so next StartAsync triggers full re-auth
            s.SpotifyAccessToken  = "";
            s.SpotifyRefreshToken = "";
            return false;
        }
    }

    // ── Polling ───────────────────────────────────────────────────
    // Aliases used by MainWindow
    public Task StartAsync(string clientId, string clientSecret, string redirectUri)
    {
        StartPolling();
        return Task.CompletedTask;
    }
    public void Stop() => _cts.Cancel();

    public void StartPolling()
    {
        _cts = new CancellationTokenSource();
        _ = Task.Run(async () =>
        {
            while (!_cts.IsCancellationRequested)
            {
                if (_spotify != null)
                {
                    try
                    {
                        var current = await _spotify.Player.GetCurrentlyPlaying(
                            new PlayerCurrentlyPlayingRequest());

                        TrackInfo? info = null;
                        if (current?.Item is FullTrack track)
                        {
                            info = new TrackInfo(
                                TrackName:  track.Name,
                                ArtistName: string.Join(", ", track.Artists.Select(a => a.Name)),
                                IsPlaying:  current.IsPlaying);
                        }

                        if (!Equals(info, _last))
                        {
                            _last = info;
                            TrackChanged?.Invoke(info);
                        }
                    }
                    catch { /* token expired or network — keep polling */ }
                }

                await Task.Delay(3000, _cts.Token).ContinueWith(_ => { });
            }
        }, _cts.Token);
    }

    public async Task StopAsync()
    {
        _cts.Cancel();
        _listener?.Stop();
        _listener = null;
        _spotify  = null;
        _last     = null;
        await Task.Delay(100);
        TrackChanged?.Invoke(null);
    }

    public void Dispose() => StopAsync().GetAwaiter().GetResult();
}
