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
    private readonly DispatcherTimer _heartTimer = new() { Interval = TimeSpan.FromMilliseconds(600) };
    private bool _heartBig;

    public ViewerWindow(string roomCode, OscService? osc = null)
    {
        InitializeComponent();

        _roomCode = roomCode.ToUpperInvariant();
        _osc      = osc;
        FriendLbl.Text = $"Partner  {_roomCode}";

        // Position: bottom-right, offset from broadcaster overlay
        var wa = SystemParameters.WorkArea;
        Left = wa.Right - Width - 20;
        Top  = wa.Bottom - 360;

        // Heart animation
        _heartTimer.Tick += HeartTimer_Tick;
        _heartTimer.Start();

        // Start watching
        _sharing.BpmReceived   += OnBpmReceived;
        _sharing.StatusChanged += OnStatusChanged;
        _ = _sharing.StartViewingAsync(_roomCode);
    }

    // ── Sharing callbacks ─────────────────────────────────────────
    private void OnBpmReceived(int bpm)
    {
        // Send partner's BPM to VRChat avatar OSC parameter (couples feature)
        var s = AppSettings.Instance;
        if (s.FriendHrOscEnabled && _osc != null && bpm > 0)
        {
            _osc.UpdateTarget(s.OscIp, s.OscPort);
            _osc.SendBpm(bpm, s.FriendHrOscParam, s.FriendHrOscParam);
        }

        Dispatcher.Invoke(() =>
        {
            BpmLbl.Text = bpm > 0 ? bpm.ToString() : "--";

            // Colour by BPM range (viewer uses fixed tiers — no personal settings)
            var (color, status) = bpm >= 140 ? ("#FFff4444", $"HIGH  ▲ {bpm} BPM") :
                                  bpm >= 100 ? ("#FFffaa33", $"MED   ~ {bpm} BPM") :
                                               ("#FF44cc77", $"LOW   ▼ {bpm} BPM");

            BpmLbl.Foreground   = (Brush)new BrushConverter().ConvertFrom(color)!;
            HeartLbl.Foreground = (Brush)new BrushConverter().ConvertFrom(color)!;
            StatusLbl.Text      = status;
            StatusLbl.Foreground = (Brush)new BrushConverter().ConvertFrom(color)!;

            // Heart speed
            _heartTimer.Interval = bpm > 0
                ? TimeSpan.FromMilliseconds(Math.Max(200, 30000 / bpm))
                : TimeSpan.FromMilliseconds(600);
        });
    }

    private void OnStatusChanged(string status)
    {
        Dispatcher.Invoke(() =>
        {
            var (dotColor, label) = status switch
            {
                "connected"    => ("#FF44cc77", "live"),
                "connecting"   => ("#FFffaa33", "connecting…"),
                "reconnecting" => ("#FFffaa33", "reconnecting…"),
                "error"        => ("#FFff4444", "connection error"),
                _              => ("#FF333344", "disconnected"),
            };

            ConnDot.Fill = (Brush)new BrushConverter().ConvertFrom(dotColor)!;
            ConnLbl.Text = label;
            ConnLbl.Foreground = (Brush)new BrushConverter().ConvertFrom(dotColor)!;

            if (status == "connected")
                StatusLbl.Text = "waiting for data…";
        });
    }

    // ── Heart animation ───────────────────────────────────────────
    private void HeartTimer_Tick(object? sender, EventArgs e)
    {
        _heartBig = !_heartBig;
        var target = _heartBig ? 1.2 : 1.0;
        var anim = new DoubleAnimation(target, TimeSpan.FromMilliseconds(120))
        {
            EasingFunction = new SineEase { EasingMode = EasingMode.EaseOut }
        };
        HeartScale.BeginAnimation(ScaleTransform.ScaleXProperty, anim);
        HeartScale.BeginAnimation(ScaleTransform.ScaleYProperty, anim);
    }

    // ── UI events ─────────────────────────────────────────────────
    private void CloseBtn_Click(object sender, RoutedEventArgs e) => Close();

    private void Window_MouseLeftButtonDown(object sender, MouseButtonEventArgs e) => DragMove();

    private void Window_Closing(object sender, System.ComponentModel.CancelEventArgs e)
    {
        _heartTimer.Stop();
        _sharing.StopViewing();
        _sharing.Dispose();
    }
}
