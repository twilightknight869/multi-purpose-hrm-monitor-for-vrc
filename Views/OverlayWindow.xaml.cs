using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Shapes;
using System.Windows.Threading;
using HRMMonitor.Models;
using HRMMonitor.Services;

namespace HRMMonitor.Views;

public partial class OverlayWindow : Window
{
    // ── BPM graph ring-buffer ─────────────────────────────────────
    private const int GraphPoints = 60;
    private readonly int[] _history = new int[GraphPoints];
    private int _histIdx;
    private bool _hasData;

    // ── Heart beat animation ──────────────────────────────────────
    private readonly DispatcherTimer _heartTimer = new() { Interval = TimeSpan.FromMilliseconds(500) };
    private bool _heartBig;

    // ── Heartbeat sound ───────────────────────────────────────────
    private readonly HeartbeatPlayer _heartbeat = new();

    // ── Shake ─────────────────────────────────────────────────────
    private readonly DispatcherTimer _shakeTimer = new() { Interval = TimeSpan.FromMilliseconds(40) };
    private int    _shakeSteps;
    private double _shakeOrigLeft, _shakeOrigTop;
    private readonly Random _rng = new();

    public OverlayWindow()
    {
        InitializeComponent();

        // Position: bottom-right corner with margin
        var wa = SystemParameters.WorkArea;
        Left = wa.Right - Width - 20;
        Top  = wa.Bottom - 200;

        // Heart beat timer
        _heartTimer.Tick += HeartTimer_Tick;
        _heartTimer.Start();

        // Shake timer
        _shakeTimer.Tick += ShakeTimer_Tick;
    }

    // ── Public API (called from MainWindow) ───────────────────────
    public void SetBpm(int bpm)
    {
        // Update ring buffer
        _history[_histIdx % GraphPoints] = bpm;
        _histIdx++;
        _hasData = true;

        // BPM label
        BpmLbl.Text = bpm > 0 ? bpm.ToString() : "--";

        // Colour tiers
        var s = AppSettings.Instance;
        var (color, tier) = bpm >= s.BpmHigh ? ("#FFff4444", $"HIGH  ▲ {bpm} BPM") :
                            bpm >= s.BpmMed  ? ("#FFffaa33", $"MED   ~ {bpm} BPM") :
                                               ("#FF44cc77", $"LOW   ▼ {bpm} BPM");

        BpmLbl.Foreground = (Brush)new BrushConverter().ConvertFrom(color)!;
        HeartLbl.Foreground = (Brush)new BrushConverter().ConvertFrom(color)!;
        TierLbl.Text = tier;
        TierLbl.Foreground = (Brush)new BrushConverter().ConvertFrom(color)!;

        // Heart beat speed — scales with actual BPM
        _heartTimer.Interval = bpm > 0
            ? TimeSpan.FromMilliseconds(Math.Max(150, 60000 / bpm / 2))
            : TimeSpan.FromMilliseconds(500);

        // Heartbeat sound — matches heart animation speed
        _heartbeat.SetBpm(bpm);

        // Shake on high BPM
        if (s.ShakeEnabled && bpm >= s.BpmHigh && !_shakeTimer.IsEnabled)
            StartShake();
        else if (bpm < s.BpmHigh && _shakeTimer.IsEnabled)
            StopShake();

        // Redraw graph
        DrawGraph(bpm);
    }

    public void SetDevUser(string username)
    {
        if (string.IsNullOrEmpty(username))
        {
            DevBadge.Visibility = Visibility.Collapsed;
        }
        else
        {
            DevLbl.Text = $"DEVELOPER  •  {username}";
            DevBadge.Visibility = Visibility.Visible;
        }
    }

    public void SetSoundEnabled(bool on) => _heartbeat.Enabled = on;

    public void SetTrack(string track, string artist)
    {
        if (string.IsNullOrEmpty(track))
        {
            TrackLbl.Visibility = Visibility.Collapsed;
        }
        else
        {
            TrackLbl.Text = string.IsNullOrEmpty(artist)
                ? $"♪  {track}"
                : $"♪  {track}  —  {artist}";
            TrackLbl.Visibility = Visibility.Visible;
        }
    }

    // ── Heart pulse animation ─────────────────────────────────────
    private void HeartTimer_Tick(object? sender, EventArgs e)
    {
        _heartBig = !_heartBig;
        var target = _heartBig ? 1.25 : 1.0;

        var anim = new DoubleAnimation(target, TimeSpan.FromMilliseconds(120))
        {
            EasingFunction = new SineEase { EasingMode = EasingMode.EaseOut }
        };
        HeartScaleTransform.BeginAnimation(ScaleTransform.ScaleXProperty, anim);
        HeartScaleTransform.BeginAnimation(ScaleTransform.ScaleYProperty, anim);
    }

    // ── BPM graph ─────────────────────────────────────────────────
    private void DrawGraph(int latestBpm)
    {
        GraphCanvas.Children.Clear();
        if (!_hasData) return;

        double w = GraphCanvas.ActualWidth > 0 ? GraphCanvas.ActualWidth : 192;
        double h = GraphCanvas.ActualHeight;

        // Collect ordered history
        var pts = new int[GraphPoints];
        for (int i = 0; i < GraphPoints; i++)
            pts[i] = _history[(_histIdx - GraphPoints + i + GraphPoints * 2) % GraphPoints];

        int max = pts.Max();
        int min = pts.Min();
        if (max == min) max = min + 1;

        double stepX = w / (GraphPoints - 1);

        // Build polyline
        var poly = new Polyline { StrokeThickness = 1.5 };

        var s = AppSettings.Instance;
        var stroke = latestBpm >= s.BpmHigh ? "#FFff4444" :
                     latestBpm >= s.BpmMed  ? "#FFffaa33" : "#FF44cc77";
        poly.Stroke = (Brush)new BrushConverter().ConvertFrom(stroke)!;

        for (int i = 0; i < GraphPoints; i++)
        {
            if (pts[i] == 0) continue;
            double x = i * stepX;
            double y = h - (pts[i] - min) / (double)(max - min) * (h - 4) - 2;
            poly.Points.Add(new Point(x, y));
        }

        GraphCanvas.Children.Add(poly);

        // Horizontal reference line at mid threshold
        if (s.BpmMed > min && s.BpmMed < max)
        {
            double refY = h - (s.BpmMed - min) / (double)(max - min) * (h - 4) - 2;
            var refLine = new Line
            {
                X1 = 0, X2 = w, Y1 = refY, Y2 = refY,
                Stroke = new SolidColorBrush(Color.FromArgb(60, 255, 170, 51)),
                StrokeThickness = 0.5,
                StrokeDashArray = new DoubleCollection { 4, 4 }
            };
            GraphCanvas.Children.Add(refLine);
        }
    }

    // ── Screen shake ──────────────────────────────────────────────
    private void StartShake()
    {
        _shakeOrigLeft = Left;
        _shakeOrigTop  = Top;
        _shakeSteps    = 0;
        _shakeTimer.Start();
    }

    private void StopShake()
    {
        _shakeTimer.Stop();
        Left = _shakeOrigLeft;
        Top  = _shakeOrigTop;
    }

    private void ShakeTimer_Tick(object? sender, EventArgs e)
    {
        _shakeSteps++;
        if (_shakeSteps >= 8)
        {
            Left = _shakeOrigLeft;
            Top  = _shakeOrigTop;
            _shakeSteps = 0;
            return;
        }
        double mag = 3;
        Left = _shakeOrigLeft + (_rng.NextDouble() * 2 - 1) * mag;
        Top  = _shakeOrigTop  + (_rng.NextDouble() * 2 - 1) * mag;
    }

    // ── Right-click: toggle always-on-top ────────────────────────
    private void Window_MouseRightButtonDown(object sender, MouseButtonEventArgs e)
    {
        Topmost = !Topmost;
        // Flash the border briefly to indicate the state change
        RootBorder.BorderBrush = Topmost
            ? new SolidColorBrush(Color.FromRgb(0x2e, 0x2e, 0x48))
            : new SolidColorBrush(Color.FromRgb(0xff, 0xaa, 0x33));
    }

    // ── Cleanup ───────────────────────────────────────────────────
    protected override void OnClosed(EventArgs e)
    {
        _heartTimer.Stop();
        _shakeTimer.Stop();
        _heartbeat.Dispose();
        base.OnClosed(e);
    }

    // ── Drag ─────────────────────────────────────────────────────
    private void Window_MouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        // Update shake origin so it follows the drag
        _shakeOrigLeft = Left;
        _shakeOrigTop  = Top;
        DragMove();
        _shakeOrigLeft = Left;
        _shakeOrigTop  = Top;
    }
}
