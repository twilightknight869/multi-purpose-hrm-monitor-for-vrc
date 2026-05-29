using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Animation;

namespace HRMMonitor.Views;

public partial class SplashWindow : Window
{
    public event Action? Completed;

    private static readonly (string Tag, string Color)[] _checks =
    {
        ("run",  "#FF888899"),   // placeholder — overwritten by actual checks
    };

    public SplashWindow()
    {
        InitializeComponent();
        StartProgressAnimation();
        StartHeartAnimation();
        Loaded += async (_, _) => await RunChecksAsync();
    }

    // ── Animated sliding bar ──────────────────────────────────────
    private void StartProgressAnimation()
    {
        var anim = new DoubleAnimation
        {
            From           = -80,
            To             = ActualWidth + 80,
            Duration       = TimeSpan.FromSeconds(1.4),
            RepeatBehavior = RepeatBehavior.Forever,
            EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut },
        };
        ProgressBar.BeginAnimation(System.Windows.Controls.Canvas.LeftProperty, anim);
    }

    // ── Heart pulse ───────────────────────────────────────────────
    private void StartHeartAnimation()
    {
        var timer = new System.Timers.Timer(500) { AutoReset = true };
        timer.Elapsed += (_, _) => Dispatcher.Invoke(() =>
        {
            HeartLbl.Foreground = HeartLbl.Foreground is SolidColorBrush b &&
                                  b.Color == Color.FromRgb(0xcc, 0, 0)
                ? new SolidColorBrush(Color.FromRgb(0x55, 0, 0))
                : new SolidColorBrush(Color.FromRgb(0xcc, 0, 0));
        });
        timer.Start();
    }

    // ── Startup checks ────────────────────────────────────────────
    private async Task RunChecksAsync()
    {
        await Task.Delay(600);   // brief intro pause

        await LogLine("ok",  $"HRM Monitor v2.0.1");
        await LogLine("ok",  $".NET {Environment.Version}  ·  Windows");
        await Task.Delay(300);

        // Check settings
        var token = Models.AppSettings.Instance.PulsoidToken;
        if (!string.IsNullOrEmpty(token) && token != "YOUR_PULSOID_TOKEN")
            await LogLine("ok",  "Pulsoid token found");
        else
            await LogLine("warn", "No Pulsoid token — add it in Settings");

        await Task.Delay(300);
        await LogLine("run",  "Checking for updates…");
        SetStatus("Checking for updates…");

        // Quick update check (3 s timeout)
        try
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(3));
            using var http = new System.Net.Http.HttpClient();
            http.DefaultRequestHeaders.UserAgent.ParseAdd("HRMMonitor/2.0.0");
            var json = await http.GetStringAsync(
                "https://api.github.com/repos/twilightknight869/Multi-Purpose-HRM-Monitor-For-VRC/releases/latest",
                cts.Token);
            using var doc = System.Text.Json.JsonDocument.Parse(json);
            var tag = doc.RootElement.GetProperty("tag_name").GetString()?.TrimStart('v') ?? "";
            await LogLine("ok", $"v{tag} available on GitHub");
        }
        catch
        {
            await LogLine("info", "Update check skipped (no internet)");
        }

        await Task.Delay(400);
        await LogLine("ok", "All systems nominal");
        SetStatus("Launching…");

        await Task.Delay(1200);

        Dispatcher.Invoke(() =>
        {
            Close();
            Completed?.Invoke();
        });
    }

    private async Task LogLine(string tag, string text)
    {
        await Task.Delay(180);
        Dispatcher.Invoke(() =>
        {
            var color = tag switch
            {
                "ok"   => "#FF44ff88",
                "warn" => "#FFffaa33",
                "error"=> "#FFff4444",
                "info" => "#FF4488cc",
                _      => "#FF888899",
            };
            var badge = tag switch
            {
                "ok"   => " OK ",
                "warn" => "WARN",
                "error"=> "FAIL",
                "info" => "INFO",
                _      => " ·· ",
            };

            var row = new TextBlock { FontFamily = new FontFamily("Consolas"), FontSize = 11, Margin = new Thickness(0, 2, 0, 0) };
            row.Inlines.Add(new System.Windows.Documents.Run("[") { Foreground = new SolidColorBrush(Color.FromRgb(0x33, 0x33, 0x44)) });
            row.Inlines.Add(new System.Windows.Documents.Run(badge) { Foreground = (Brush)new BrushConverter().ConvertFrom(color)! });
            row.Inlines.Add(new System.Windows.Documents.Run("]  ") { Foreground = new SolidColorBrush(Color.FromRgb(0x33, 0x33, 0x44)) });
            row.Inlines.Add(new System.Windows.Documents.Run(text)  { Foreground = new SolidColorBrush(Color.FromRgb(0xaa, 0xaa, 0xbb)) });

            LogPanel.Children.Add(row);
            LogScroll.ScrollToBottom();
            SetStatus(text);
        });
    }

    private void SetStatus(string text)
    {
        StatusLbl.Text = text.Length > 60 ? text[..60] : text;
    }
}
