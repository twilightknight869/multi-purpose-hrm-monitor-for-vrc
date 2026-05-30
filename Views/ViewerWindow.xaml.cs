using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Threading;
using HRMMonitor.Models;
using HRMMonitor.Services;

namespace HRMMonitor.Views;

public partial class ViewerWindow : Window
{
    private readonly string          _roomCode;
    private readonly SharingService  _sharing = new();
    private readonly OscService?     _osc;
    private readonly HeartbeatPlayer _heartbeat = new();
    private System.Action<string, int>? _onGroupBpm; // callback to notify SteamVR service

    // ── Heart animation ───────────────────────────────────────────
    private readonly DispatcherTimer _heartTimer = new() { Interval = TimeSpan.FromMilliseconds(600) };
    private bool _heartBig;

    // ── Screen shake ──────────────────────────────────────────────
    private readonly DispatcherTimer _shakeTimer = new() { Interval = TimeSpan.FromMilliseconds(40) };
    private int    _shakeSteps;
    private double _shakeOrigLeft, _shakeOrigTop;
    private readonly Random _rng = new();
    private int _lastBpm;

    public ViewerWindow(string roomCode, OscService? osc = null,
                        System.Action<string, int>? onGroupBpm = null)
    {
        InitializeComponent();

        _roomCode    = roomCode.ToUpperInvariant();
        _osc         = osc;
        _onGroupBpm  = onGroupBpm;
        FriendLbl.Text = $"Partner  {_roomCode}";

        // Position: bottom-right, offset from broadcaster overlay
        var wa = SystemParameters.WorkArea;
        Left = wa.Right - Width - 20;
        Top  = wa.Bottom - 360;

        _heartTimer.Tick += HeartTimer_Tick;
        _heartTimer.Start();

        _shakeTimer.Tick += ShakeTimer_Tick;

        _heartbeat.Enabled = AppSettings.Instance.HeartbeatSoundEnabled;

        _sharing.BpmReceived   += OnBpmReceived;
        _sharing.StatusChanged += OnStatusChanged;
        _ = _sharing.StartViewingAsync(_roomCode);
    }

    // ── BPM received ──────────────────────────────────────────────
    private void OnBpmReceived(int bpm)
    {
        // Send partner BPM to VRChat avatar OSC
        var s = AppSettings.Instance;
        if (s.FriendHrOscEnabled && _osc != null && bpm > 0)
        {
            _osc.UpdateTarget(s.OscIp, s.OscPort);
            _osc.SendBpm(bpm, s.FriendHrOscParam, s.FriendHrOscParam);
        }

        _onGroupBpm?.Invoke(_roomCode, bpm);
        Dispatcher.Invoke(() => UpdateBpm(bpm));
    }

    private void UpdateBpm(int bpm)
    {
        _lastBpm = bpm;
        BpmLbl.Text = bpm > 0 ? bpm.ToString() : "--";

        var s    = AppSettings.Instance;
        int high = s.BpmHigh;
        int med  = s.BpmMed;

        // Colour tiers matching broadcaster overlay
        var (color, status) = bpm >= high
            ? ("#FFff4444", $"HIGH  ^ {bpm} BPM")
            : bpm >= med
            ? ("#FFffaa33", $"MED   ~ {bpm} BPM")
            : ("#FF44cc77", $"LOW   v {bpm} BPM");

        var brush = (Brush)new BrushConverter().ConvertFrom(color)!;
        BpmLbl.Foreground   = brush;
        HeartLbl.Foreground = brush;
        StatusLbl.Text      = status;
        StatusLbl.Foreground = brush;

        // Heart pulse speed scales with BPM
        _heartTimer.Interval = bpm > 0
            ? TimeSpan.FromMilliseconds(Math.Max(150, 60000 / bpm / 2))
            : TimeSpan.FromMilliseconds(600);

        // Heartbeat sound
        _heartbeat.SetBpm(bpm);

        // Screen shake on high BPM
        if (bpm >= high && !_shakeTimer.IsEnabled)
            StartShake();
        else if (bpm < high && _shakeTimer.IsEnabled)
            StopShake();
    }

    // ── Status received ───────────────────────────────────────────
    private void OnStatusChanged(string status)
    {
        Dispatcher.Invoke(() =>
        {
            var (dotColor, label) = status switch
            {
                "connected"    => ("#FF44cc77", "live"),
                "connecting"   => ("#FFffaa33", "connecting..."),
                "reconnecting" => ("#FFffaa33", "reconnecting..."),
                "error"        => ("#FFff4444", "connection error"),
                _              => ("#FF333344", "disconnected"),
            };
            ConnDot.Fill = (Brush)new BrushConverter().ConvertFrom(dotColor)!;
            ConnLbl.Text = label;
            ConnLbl.Foreground = (Brush)new BrushConverter().ConvertFrom(dotColor)!;
            if (status == "connected") StatusLbl.Text = "waiting for data...";
        });
    }

    // ── Heart animation ───────────────────────────────────────────
    private void HeartTimer_Tick(object? sender, EventArgs e)
    {
        _heartBig = !_heartBig;
        double scale = _heartBig ? 1.25 : 1.0;
        var anim = new DoubleAnimation(scale, TimeSpan.FromMilliseconds(100))
        {
            EasingFunction = new SineEase { EasingMode = EasingMode.EaseOut }
        };
        HeartScale.BeginAnimation(ScaleTransform.ScaleXProperty, anim);
        HeartScale.BeginAnimation(ScaleTransform.ScaleYProperty, anim);
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
        // Shake magnitude scales slightly with how far above the threshold
        double mag = Math.Min(4, 2 + (_lastBpm - AppSettings.Instance.BpmHigh) / 30.0);
        if (_shakeSteps >= 8)
        {
            Left = _shakeOrigLeft;
            Top  = _shakeOrigTop;
            _shakeSteps = 0;
            return;
        }
        Left = _shakeOrigLeft + (_rng.NextDouble() * 2 - 1) * mag;
        Top  = _shakeOrigTop  + (_rng.NextDouble() * 2 - 1) * mag;
    }

    // ── UI events ─────────────────────────────────────────────────
    private void CloseBtn_Click(object sender, RoutedEventArgs e) => Close();
    private void Window_MouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        _shakeOrigLeft = Left;
        _shakeOrigTop  = Top;
        DragMove();
        _shakeOrigLeft = Left;
        _shakeOrigTop  = Top;
    }

    private void Window_Closing(object sender, System.ComponentModel.CancelEventArgs e)
    {
        _heartTimer.Stop();
        _shakeTimer.Stop();
        _heartbeat.Dispose();
        _sharing.StopViewing();
        _sharing.Dispose();
    }
}
