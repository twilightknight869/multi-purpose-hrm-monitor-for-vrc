using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json;

namespace HRMMonitor.Services;

/// <summary>
/// Friend HR Sharing via the HRM bot relay server (Railway).
/// No rate limits — your own server, persistent SSE connections.
///
/// HOST:   POST {ApiUrl}/relay/{ROOMCODE}   every 2 s
/// VIEWER: GET  {ApiUrl}/relay/{ROOMCODE}/sse  (SSE stream)
///
/// Both sides send x-hrm-secret so only the HRM app can use the relay.
/// </summary>
public class SharingService : IDisposable
{
    // ── Relay config (must match your Railway bot's .env) ─────────
    // Set ApiUrl in LicenseService.cs after you deploy the bot.
    private static string RelayBase   => LicenseService.ApiUrl.TrimEnd('/');
    private static string RelaySecret => LicenseService.ApiSecret;

    private readonly HttpClient              _http = new();
    private          CancellationTokenSource _cts  = new();

    public event Action<int>?    BpmReceived;
    public event Action<string>? StatusChanged;

    // ── HOST: single-shot publish ──────────────────────────────────
    public async Task PublishBpmAsync(string roomCode, int bpm)
    {
        try
        {
            var url = $"{RelayBase}/relay/{roomCode.ToUpperInvariant()}";
            var req = new HttpRequestMessage(HttpMethod.Post, url);
            req.Headers.Add("x-hrm-secret", RelaySecret);
            req.Content = new StringContent(
                JsonSerializer.Serialize(new { bpm }),
                Encoding.UTF8, "application/json");
            await _http.SendAsync(req);
        }
        catch { /* network blip — silent */ }
    }

    // ── VIEWER aliases ─────────────────────────────────────────────
    public Task StartViewingAsync(string roomCode) => StartViewerAsync(roomCode);
    public void StopViewing() => _ = StopAsync();

    public async Task StartViewerAsync(string roomCode)
    {
        await StopAsync();
        _cts = new CancellationTokenSource();

        var sseUrl = $"{RelayBase}/relay/{roomCode.ToUpperInvariant()}/sse";

        _ = Task.Run(async () =>
        {
            while (!_cts.IsCancellationRequested)
            {
                StatusChanged?.Invoke("connecting");
                try
                {
                    using var req = new HttpRequestMessage(HttpMethod.Get, sseUrl);
                    req.Headers.Add("x-hrm-secret", RelaySecret);
                    req.Headers.Accept.ParseAdd("text/event-stream");

                    using var resp = await _http.SendAsync(req,
                        HttpCompletionOption.ResponseHeadersRead, _cts.Token);

                    resp.EnsureSuccessStatusCode();
                    StatusChanged?.Invoke("connected");

                    using var stream = await resp.Content.ReadAsStreamAsync(_cts.Token);
                    using var reader = new StreamReader(stream);

                    while (!_cts.IsCancellationRequested)
                    {
                        var line = await reader.ReadLineAsync(_cts.Token);
                        if (line == null) break;

                        // Skip SSE comments (keepalives) and empty lines
                        if (string.IsNullOrWhiteSpace(line) || line.StartsWith(':')) continue;

                        if (line.StartsWith("data:"))
                        {
                            var json = line[5..].Trim();
                            TryParseBpm(json);
                        }
                    }
                }
                catch (OperationCanceledException) { break; }
                catch
                {
                    StatusChanged?.Invoke("connecting");
                    await Task.Delay(3000, _cts.Token).ContinueWith(_ => { });
                }
            }
            StatusChanged?.Invoke("disconnected");
        }, _cts.Token);
    }

    private void TryParseBpm(string json)
    {
        try
        {
            using var doc = JsonDocument.Parse(json);
            var bpm = doc.RootElement.GetProperty("bpm").GetInt32();
            if (bpm > 0) BpmReceived?.Invoke(bpm);
        }
        catch { }
    }

    public async Task StopAsync()
    {
        _cts.Cancel();
        await Task.Delay(100);
        _cts = new CancellationTokenSource();
        StatusChanged?.Invoke("disconnected");
    }

    // Legacy host loop (kept for compatibility)
    public async Task StartHostAsync(string roomCode, Func<int> getBpm)
    {
        await StopAsync();
        _cts = new CancellationTokenSource();
        StatusChanged?.Invoke("connected");
        _ = Task.Run(async () =>
        {
            while (!_cts.IsCancellationRequested)
            {
                await PublishBpmAsync(roomCode, getBpm());
                await Task.Delay(2000, _cts.Token).ContinueWith(_ => { });
            }
        }, _cts.Token);
    }

    public void Dispose()
    {
        _cts.Cancel();
        _http.Dispose();
    }
}
