using System.Net.WebSockets;
using System.Text.Json;
using Websocket.Client;

namespace HRMMonitor.Services;

/// <summary>
/// Connects to Pulsoid's real-time WebSocket and fires BpmReceived
/// whenever a new heart rate comes in.
/// </summary>
public class PulsoidService : IDisposable
{
    private const string WsUrl = "wss://dev.pulsoid.net/api/v1/data/real_time";

    private WebsocketClient? _client;
    private CancellationTokenSource _cts = new();

    public event Action<int>?    BpmReceived;
    public event Action<string>? StatusChanged;   // "connected" | "disconnected" | "error:..."

    public bool IsRunning => _client?.IsRunning ?? false;

    // Sync wrappers for fire-and-forget usage from UI thread
    public void Start(string token) => _ = StartAsync(token);
    public void Stop()              => _ = StopAsync();

    public async Task StartAsync(string token)
    {
        await StopAsync();
        _cts = new CancellationTokenSource();

        var url = new Uri($"{WsUrl}?access_token={token}");
        var factory = new Func<ClientWebSocket>(() =>
        {
            var ws = new ClientWebSocket();
            ws.Options.SetRequestHeader("Authorization", $"Bearer {token}");
            return ws;
        });

        _client = new WebsocketClient(url, factory)
        {
            ReconnectTimeout        = TimeSpan.FromSeconds(30),
            ErrorReconnectTimeout   = TimeSpan.FromSeconds(5),
            IsReconnectionEnabled   = true,
        };

        _client.ReconnectionHappened.Subscribe(info =>
        {
            StatusChanged?.Invoke("connected");
        });

        _client.DisconnectionHappened.Subscribe(info =>
        {
            StatusChanged?.Invoke("disconnected");
        });

        _client.MessageReceived.Subscribe(msg =>
        {
            try
            {
                using var doc  = JsonDocument.Parse(msg.Text ?? "{}");
                var root       = doc.RootElement;
                // Pulsoid payload: { "data": { "heart_rate": 72 } }
                if (root.TryGetProperty("data", out var data) &&
                    data.TryGetProperty("heart_rate", out var hr))
                {
                    var bpm = hr.GetInt32();
                    if (bpm > 0) BpmReceived?.Invoke(bpm);
                }
            }
            catch { /* malformed frame — ignore */ }
        });

        try
        {
            await _client.StartOrFail();
        }
        catch (Exception ex)
        {
            StatusChanged?.Invoke($"error:{ex.Message}");
        }
    }

    public async Task StopAsync()
    {
        _cts.Cancel();
        if (_client != null)
        {
            await _client.StopOrFail(WebSocketCloseStatus.NormalClosure, "user stopped");
            _client.Dispose();
            _client = null;
        }
        StatusChanged?.Invoke("disconnected");
    }

    public void Dispose() => StopAsync().GetAwaiter().GetResult();
}
