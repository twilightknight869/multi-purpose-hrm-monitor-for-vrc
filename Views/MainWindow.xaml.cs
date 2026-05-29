using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;
using HRMMonitor.Models;
using HRMMonitor.Services;

namespace HRMMonitor.Views;

public partial class MainWindow : Window
{
    // ── Services ──────────────────────────────────────────────────
    private readonly PulsoidService  _pulsoid  = new();
    private readonly OscService      _osc      = new();
    private readonly SharingService  _sharing  = new();
    private readonly SpotifyService  _spotify  = new();
    private readonly SteamVrService  _steamvr  = new();
    private readonly UpdateService   _updater  = new();
    private readonly LicenseService  _license  = new();

    // ── State ─────────────────────────────────────────────────────
    private bool          _running;
    private OverlayWindow? _overlay;
    private int           _lastBpm;
    private string        _lastTrack  = "";
    private string        _lastArtist = "";
    private bool          _suppressChanges; // prevents re-entrant setting saves

    public MainWindow()
    {
        _suppressChanges = true;   // block all event handlers during XAML init
        InitializeComponent();
        MigrateSettings();
        LoadSettings();            // re-enables _suppressChanges at the end
        WireServices();
        _updater.Start();
        _license.Start();
    }

    // ── One-time migration: reset any old template that had inline {track}/{artist} ──
    private static void MigrateSettings()
    {
        var t = AppSettings.Instance.ChatboxTemplate;
        // If old template had track/artist inline (no \n), reset to clean default
        if (t.Contains("{track}") || t.Contains("{artist}"))
        {
            AppSettings.Instance.ChatboxTemplate = "{icon} {bpm} BPM [{bar}]{track}";
        }
    }

    // ── Load saved settings into controls ─────────────────────────
    private void LoadSettings()
    {
        _suppressChanges = true;
        var s = AppSettings.Instance;

        // Token — just show placeholder dots if a token exists
        TokenBox.Password   = s.PulsoidToken;

        // OSC
        OscCheck.IsChecked      = s.OscEnabled;
        ChatboxCheck.IsChecked  = s.ChatboxEnabled;
        ChatboxTemplate.Text    = s.ChatboxTemplate;
        OscIpBox.Text           = s.OscIp;
        OscPortBox.Text         = s.OscPort.ToString();
        HrParamBox.Text         = s.OscHrParam;
        PctParamBox.Text        = s.OscPctParam;

        // Sharing
        ShareCheck.IsChecked = s.SharingEnabled;
        RoomCodeLbl.Text     = s.RoomCode;

        // Spotify
        SpotifyCheck.IsChecked = s.SpotifyEnabled;
        SpClientId.Text        = s.SpotifyClientId;
        SpClientSecret.Password = s.SpotifyClientSecret;
        SpRedirectUri.Text     = s.SpotifyRedirectUri;

        // SteamVR
        SteamVrCheck.IsChecked = s.SteamVrEnabled;

        // Settings tab
        BpmHighBox.Text = s.BpmHigh.ToString();
        BpmMedBox.Text  = s.BpmMed.ToString();
        OpacitySlider.Value = s.OverlayOpacity;
        OpacityLbl.Text     = $"{s.OverlayOpacity:P0}";
        ShakeCheck.IsChecked = s.ShakeEnabled;

        // License
        LicenseKeyBox.Text     = s.LicenseKey;
        DevTagCheck.IsChecked  = s.ShowDevTag;

        // Pronoun
        foreach (System.Windows.Controls.ComboBoxItem item in PronounBox.Items)
            if (item.Content.ToString() == s.Pronoun) { PronounBox.SelectedItem = item; break; }
        if (PronounBox.SelectedItem == null) PronounBox.SelectedIndex = 0;

        // Viewer
        ViewerCodeBox.Text       = s.ViewerRoomCode;
        FriendHrOscCheck.IsChecked = s.FriendHrOscEnabled;
        FriendHrParamBox.Text    = s.FriendHrOscParam;

        UpdatePreview();
        _suppressChanges = false;
    }

    // ── Wire service events ───────────────────────────────────────
    private void WireServices()
    {
        // Pulsoid → connection dot + BPM distribution
        _pulsoid.StatusChanged += status => Dispatcher.Invoke(() => UpdateConnStatus(status));
        _pulsoid.BpmReceived   += bpm    => Dispatcher.Invoke(() => OnBpmReceived(bpm));

        // Spotify → chatbox preview + overlay
        _spotify.TrackChanged += info => Dispatcher.Invoke(() =>
        {
            _lastTrack  = info?.TrackName  ?? "";
            _lastArtist = info?.ArtistName ?? "";
            UpdatePreview();
            _overlay?.SetTrack(_lastTrack, _lastArtist);
        });

        // SteamVR mode changes
        _steamvr.ModeChanged += mode => Dispatcher.Invoke(() =>
        {
            // Nothing needed in main window — overlay handles its own visibility
        });

        // Update checker
        _updater.UpdateAvailable += url => Dispatcher.Invoke(() => ShowUpdateAlert(url));

        // License — use BeginInvoke so sync code paths don't deadlock the UI thread
        _license.StatusChanged           += s   => Dispatcher.BeginInvoke(() => UpdateLicenseBadge(s));
        _license.SecondsRemainingChanged += sec => Dispatcher.BeginInvoke(() => UpdateFreeTimer(sec));
    }

    // ── BPM routing ───────────────────────────────────────────────
    private void OnBpmReceived(int bpm)
    {
        _lastBpm = bpm;
        _steamvr.SetBpm(bpm);
        _overlay?.SetBpm(bpm);

        var s = AppSettings.Instance;

        // OSC
        if (s.OscEnabled)
        {
            _osc.SendBpm(bpm, s.OscHrParam, s.OscPctParam);

            if (s.ChatboxEnabled)
            {
                var msg = BuildChatboxMessage(bpm);
                // Append dev tag to chatbox if dev key active
                if (_license.IsPremium && _license.ActiveDevSlot > 0)
                {
                    bool showTag = _license.ActiveDevSlot <= 3
                        ? AppSettings.Instance.ShowDevTag : true;
                    if (showTag)
                        msg += $"\n[DEV] {DevKeyManager.GetUsername(_license.ActiveDevSlot)}";
                }
                _osc.SendChatbox(msg);
            }
        }

        // Sharing
        if (s.SharingEnabled)
            _ = _sharing.PublishBpmAsync(s.RoomCode, bpm);
    }

    // ── Chatbox preview / builder ─────────────────────────────────
    private void UpdatePreview()
    {
        var msg = BuildChatboxMessage(_lastBpm);
        ChatboxPreview.Text = msg;
    }

    private string BuildChatboxMessage(int bpm)
    {
        var s = AppSettings.Instance;
        int high = s.BpmHigh;
        int med  = s.BpmMed;

        string tier = bpm >= high ? "HIGH" : bpm >= med ? "MED" : "LOW";
        // VRChat chatbox uses a limited font — use ASCII-safe chars instead of emoji/block chars
        // VRChat chatbox only supports basic ASCII — no Unicode symbols
        string icon = bpm >= high ? "!!!" : bpm >= med ? "<3" : "~";
        int    bar  = bpm > 0 ? Math.Clamp((int)Math.Round(bpm / 200.0 * 10), 0, 10) : 0;
        string barStr = new string('|', bar) + new string('-', 10 - bar);

        // {track} and {artist} always start on their own line to avoid
        // running into the BPM line in VRChat's chatbox display.
        var trackVal  = string.IsNullOrEmpty(_lastTrack)  ? "" : $"\n* {_lastTrack}";
        var artistVal = string.IsNullOrEmpty(_lastArtist) ? "" : $"\n  {_lastArtist}";

        return s.ChatboxTemplate
            .Replace("{bpm}",     bpm > 0 ? bpm.ToString() : "--")
            .Replace("{bar}",     barStr)
            .Replace("{tier}",    tier)
            .Replace("{icon}",    icon)
            .Replace("{track}",   trackVal)
            .Replace("{artist}",  artistVal)
            .Replace("{pronoun}", s.Pronoun)
            .TrimEnd();
    }

    // ── Connection status dot ─────────────────────────────────────
    private void UpdateConnStatus(string status)
    {
        var (color, label) = status switch
        {
            "connected"     => ("#FF44cc77", "connected"),
            "connecting"    => ("#FFffaa33", "connecting…"),
            "reconnecting"  => ("#FFffaa33", "reconnecting…"),
            _               => ("#FF333344", "disconnected"),
        };
        ConnDot.Fill = (Brush)new BrushConverter().ConvertFrom(color)!;
        ConnLbl.Text = label;
        ConnLbl.Foreground = (Brush)new BrushConverter().ConvertFrom(color)!;
    }

    // ── Tab selection ─────────────────────────────────────────────
    private void MainTabs_SelectionChanged(object sender, SelectionChangedEventArgs e) { }

    // ══════════════════════════════════════════════════════════════
    //  BROADCASTER TAB — control event handlers
    // ══════════════════════════════════════════════════════════════

    private void TokenBox_Changed(object sender, RoutedEventArgs e)
    {
        if (_suppressChanges) return;
        AppSettings.Instance.PulsoidToken = TokenBox.Password;
    }

    private void ShowToken_Click(object sender, RoutedEventArgs e)
    {
        // Toggle: show token in a dialog (PasswordBox can't show inline easily)
        var token = AppSettings.Instance.PulsoidToken;
        if (string.IsNullOrEmpty(token))
        {
            MessageBox.Show("No token saved.", "Pulsoid Token", MessageBoxButton.OK, MessageBoxImage.Information);
        }
        else
        {
            MessageBox.Show(token, "Pulsoid Token (keep private!)", MessageBoxButton.OK, MessageBoxImage.Information);
        }
    }

    private void OscCheck_Changed(object sender, RoutedEventArgs e)
    {
        if (_suppressChanges) return;
        AppSettings.Instance.OscEnabled = OscCheck.IsChecked == true;
    }

    private void ChatboxCheck_Changed(object sender, RoutedEventArgs e)
    {
        if (_suppressChanges) return;
        AppSettings.Instance.ChatboxEnabled = ChatboxCheck.IsChecked == true;
    }

    private void ChatboxTemplate_Changed(object sender, TextChangedEventArgs e)
    {
        if (_suppressChanges) return;
        AppSettings.Instance.ChatboxTemplate = ChatboxTemplate.Text;
        UpdatePreview();
    }

    private void OscAddr_Changed(object sender, TextChangedEventArgs e)
    {
        if (_suppressChanges) return;
        AppSettings.Instance.OscIp      = OscIpBox.Text;
        AppSettings.Instance.OscHrParam = HrParamBox.Text;
        AppSettings.Instance.OscPctParam = PctParamBox.Text;
        if (int.TryParse(OscPortBox.Text, out var port))
            AppSettings.Instance.OscPort = port;

        // Reapply to OSC service if running
        if (_running)
            _osc.UpdateTarget(AppSettings.Instance.OscIp, AppSettings.Instance.OscPort);
    }

    private void ShareCheck_Changed(object sender, RoutedEventArgs e)
    {
        if (_suppressChanges) return;
        AppSettings.Instance.SharingEnabled = ShareCheck.IsChecked == true;
    }

    private void NewCode_Click(object sender, RoutedEventArgs e)
    {
        const string chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
        var rng  = new Random();
        var code = new string(Enumerable.Range(0, 6).Select(_ => chars[rng.Next(chars.Length)]).ToArray());
        AppSettings.Instance.RoomCode = code;
        RoomCodeLbl.Text = code;
    }

    // ── Spotify ───────────────────────────────────────────────────
    private void SpotifyCheck_Changed(object sender, RoutedEventArgs e)
    {
        if (_suppressChanges) return;
        AppSettings.Instance.SpotifyEnabled = SpotifyCheck.IsChecked == true;
    }

    // Called by TextBox.TextChanged (SpClientId, SpRedirectUri)
    private void SpotifyText_Changed(object sender, TextChangedEventArgs e)
    {
        if (_suppressChanges) return;
        AppSettings.Instance.SpotifyClientId    = SpClientId.Text;
        AppSettings.Instance.SpotifyRedirectUri = SpRedirectUri.Text;
    }

    // Called by PasswordBox.PasswordChanged (SpClientSecret)
    private void SpotifySecret_Changed(object sender, RoutedEventArgs e)
    {
        if (_suppressChanges) return;
        AppSettings.Instance.SpotifyClientSecret = SpClientSecret.Password;
    }

    private async void SpotifyAuth_Click(object sender, RoutedEventArgs e)
    {
        var s = AppSettings.Instance;
        if (string.IsNullOrWhiteSpace(s.SpotifyClientId) ||
            string.IsNullOrWhiteSpace(s.SpotifyClientSecret))
        {
            MessageBox.Show("Enter your Spotify Client ID and Secret first.",
                "Spotify", MessageBoxButton.OK, MessageBoxImage.Warning);
            return;
        }

        try
        {
            await _spotify.AuthorizeAsync(s.SpotifyClientId, s.SpotifyClientSecret, s.SpotifyRedirectUri);
            MessageBox.Show("Spotify authorized!", "Spotify", MessageBoxButton.OK, MessageBoxImage.Information);
        }
        catch (Exception ex)
        {
            MessageBox.Show($"Spotify auth failed:\n{ex.Message}", "Spotify",
                MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }

    // ── SteamVR ───────────────────────────────────────────────────
    private void SteamVrCheck_Changed(object sender, RoutedEventArgs e)
    {
        if (_suppressChanges) return;
        AppSettings.Instance.SteamVrEnabled = SteamVrCheck.IsChecked == true;
        if (SteamVrCheck.IsChecked == true && _running)
            _steamvr.Start();
        else if (SteamVrCheck.IsChecked == false)
            _steamvr.Stop();
    }

    // ── START / STOP ──────────────────────────────────────────────
    private void Start_Click(object sender, RoutedEventArgs e)
    {
        if (!_running) StartOverlay();
        else           StopOverlay();
    }

    private void StartOverlay()
    {
        var s = AppSettings.Instance;
        if (string.IsNullOrWhiteSpace(s.PulsoidToken))
        {
            MessageBox.Show("Add your Pulsoid token first.", "HRM Monitor",
                MessageBoxButton.OK, MessageBoxImage.Warning);
            return;
        }

        _running = true;
        StartBtn.Content = "■   STOP OVERLAY";

        // Start services
        _osc.UpdateTarget(s.OscIp, s.OscPort);
        _pulsoid.Start(s.PulsoidToken);

        if (s.SteamVrEnabled)
            _steamvr.Start();

        if (s.SpotifyEnabled)
            _ = _spotify.StartAsync(s.SpotifyClientId, s.SpotifyClientSecret, s.SpotifyRedirectUri);

        // Open overlay
        _overlay = new OverlayWindow();
        _overlay.Opacity = s.OverlayOpacity;
        _overlay.Show();

        // Show dev badge if a dev key is active
        if (_license.IsPremium && _license.ActiveDevSlot > 0)
        {
            var devName = DevKeyManager.GetUsername(_license.ActiveDevSlot);
            bool showTag = _license.ActiveDevSlot <= 3
                ? AppSettings.Instance.ShowDevTag
                : true;  // slots 4-6 always show tag (no toggle)
            _overlay.SetDevUser(showTag ? devName : "");

            // Show toggle checkbox only for slots 1-3
            DevTagCheck.Visibility = _license.ActiveDevSlot <= 3
                ? Visibility.Visible : Visibility.Collapsed;
        }
    }

    private void StopOverlay()
    {
        _running = false;
        StartBtn.Content = "▶   START OVERLAY";

        _pulsoid.Stop();
        _steamvr.Stop();
        _spotify.Stop();

        _overlay?.Close();
        _overlay = null;

        UpdateConnStatus("disconnected");
    }

    // ══════════════════════════════════════════════════════════════
    //  VIEWER TAB
    // ══════════════════════════════════════════════════════════════

    private void ViewerCode_Changed(object sender, TextChangedEventArgs e)
    {
        if (_suppressChanges) return;
        AppSettings.Instance.ViewerRoomCode = ViewerCodeBox.Text.ToUpperInvariant();
    }

    private void FriendHrOsc_Changed(object sender, RoutedEventArgs e)
    {
        if (_suppressChanges) return;
        AppSettings.Instance.FriendHrOscEnabled = FriendHrOscCheck.IsChecked == true;
    }

    private void FriendHrParam_Changed(object sender, TextChangedEventArgs e)
    {
        if (_suppressChanges) return;
        AppSettings.Instance.FriendHrOscParam = FriendHrParamBox.Text;
    }

    private void Watch_Click(object sender, RoutedEventArgs e)
    {
        var code = ViewerCodeBox.Text.Trim().ToUpperInvariant();
        if (code.Length != 6)
        {
            MessageBox.Show("Enter a 6-character room code.", "Viewer",
                MessageBoxButton.OK, MessageBoxImage.Warning);
            return;
        }

        AppSettings.Instance.ViewerRoomCode = code;

        var win = new ViewerWindow(code, _osc);
        win.Show();
    }

    // ══════════════════════════════════════════════════════════════
    //  SETTINGS TAB
    // ══════════════════════════════════════════════════════════════

    private void Pronoun_Changed(object sender, System.Windows.Controls.SelectionChangedEventArgs e)
    {
        if (_suppressChanges) return;
        if (PronounBox.SelectedItem is System.Windows.Controls.ComboBoxItem item)
        {
            AppSettings.Instance.Pronoun = item.Content.ToString() ?? "My";
            UpdatePreview();
        }
    }

    // ── License handlers ──────────────────────────────────────────
    private void DevTag_Changed(object sender, RoutedEventArgs e)
    {
        if (_suppressChanges) return;
        AppSettings.Instance.ShowDevTag = DevTagCheck.IsChecked == true;

        // Update overlay live
        if (_overlay != null && _license.ActiveDevSlot > 0)
        {
            var show = DevTagCheck.IsChecked == true;
            _overlay.SetDevUser(show ? DevKeyManager.GetUsername(_license.ActiveDevSlot) : "");
        }
    }

    private void LicenseKey_Changed(object sender, TextChangedEventArgs e)
    {
        if (_suppressChanges) return;
        AppSettings.Instance.LicenseKey = LicenseKeyBox.Text.Trim();
    }

    private async void LicenseActivate_Click(object sender, RoutedEventArgs e)
    {
        AppSettings.Instance.LicenseKey = LicenseKeyBox.Text.Trim();
        LicenseLbl.Text = "Checking…";
        LicenseDot.Fill = (Brush)new BrushConverter().ConvertFrom("#FFffaa33")!;

        // Run check on background thread so sync dev-key path doesn't block UI
        await Task.Run(() => _license.CheckAsync());

        // If a dev key was detected, open the password/HWID window directly here
        // (not via BeginInvoke so it's always in response to the button click)
        if (_license.Status == LicenseStatus.DevKeyPending)
        {
            var win = new DevKeyWindow(
                _license.ActiveDevSlot,
                _license.LastDevKeyResult == DevKeyManager.DevKeyResult.HwidNotBound ||
                _license.LastDevKeyResult == DevKeyManager.DevKeyResult.HwidMismatch,
                _license.LastDevKeyResult,
                onSuccess: () =>
                {
                    _license.SetStatus_Internal(LicenseStatus.Premium);
                    _license.StopUsageTracking();
                });
            win.Owner = this;
            win.ShowDialog();
        }
    }

    private void UpdateLicenseBadge(LicenseStatus status)
    {
        // Hide free timer and show dev toggle when premium is confirmed
        if (status == LicenseStatus.Premium)
        {
            FreeTimeLbl.Visibility = Visibility.Collapsed;
            if (_license.ActiveDevSlot >= 1 && _license.ActiveDevSlot <= 3)
                DevTagCheck.Visibility = Visibility.Visible;
        }
        else
        {
            DevTagCheck.Visibility = Visibility.Collapsed;
        }

        // Dev key pending — just update the badge; DevKeyWindow is opened only
        // from the Activate button click, not automatically.
        if (status == LicenseStatus.DevKeyPending)
        {
            LicenseDot.Fill  = (Brush)new BrushConverter().ConvertFrom("#FFffaa33")!;
            LicenseLbl.Text  = "Dev key found — click Activate to set password";
            LicenseLbl.Foreground = (Brush)new BrushConverter().ConvertFrom("#FFffaa33")!;
            return;
        }

        var (color, text) = status switch
        {
            LicenseStatus.Premium          => ("#FF44cc77", "✓  Dev/Premium — unlimited + all features"),
            LicenseStatus.Free             => ("#FF4488cc", $"Free tier — {LicenseService.FormatLimit()} per day"),
            LicenseStatus.FreeLimitReached => ("#FFff4444", "Daily limit reached — restart tomorrow or upgrade"),
            LicenseStatus.Invalid          => ("#FFff4444", "Invalid key — check and try again"),
            LicenseStatus.Revoked          => ("#FFff4444", "License revoked — contact support"),
            _                              => ("#FF444455", "Checking license…"),
        };

        LicenseDot.Fill = (Brush)new BrushConverter().ConvertFrom(color)!;
        LicenseLbl.Text = text;
        LicenseLbl.Foreground = (Brush)new BrushConverter().ConvertFrom(color)!;

        if (status == LicenseStatus.FreeLimitReached)
        {
            // Block the start button
            StartBtn.IsEnabled = false;
            StartBtn.Content   = "■  DAILY LIMIT REACHED";
            if (_running) StopOverlay();
        }
        else if (!_running)
        {
            StartBtn.IsEnabled = true;
            StartBtn.Content   = "▶   START OVERLAY";
        }

        // Start usage tracking when free/limit reached
        if (status == LicenseStatus.Free)
            _license.StartUsageTracking();
        else
            _license.StopUsageTracking();
    }

    private void UpdateFreeTimer(int secondsRemaining)
    {
        if (_license.IsPremium) { FreeTimeLbl.Visibility = Visibility.Collapsed; return; }
        var h = secondsRemaining / 3600;
        var m = (secondsRemaining % 3600) / 60;
        var s = secondsRemaining % 60;
        FreeTimeLbl.Text       = $"Free time remaining today: {h}h {m:D2}m {s:D2}s";
        FreeTimeLbl.Visibility = Visibility.Visible;
    }

    private void BpmThresh_Changed(object sender, TextChangedEventArgs e)
    {
        if (_suppressChanges) return;
        if (int.TryParse(BpmHighBox.Text, out var h)) AppSettings.Instance.BpmHigh = h;
        if (int.TryParse(BpmMedBox.Text,  out var m)) AppSettings.Instance.BpmMed  = m;
        UpdatePreview();
    }

    private void Opacity_Changed(object sender, RoutedPropertyChangedEventArgs<double> e)
    {
        if (_suppressChanges) return;
        var val = OpacitySlider.Value;
        AppSettings.Instance.OverlayOpacity = val;
        OpacityLbl.Text = $"{val:P0}";
        if (_overlay != null) _overlay.Opacity = val;
    }

    private void ShakeCheck_Changed(object sender, RoutedEventArgs e)
    {
        if (_suppressChanges) return;
        AppSettings.Instance.ShakeEnabled = ShakeCheck.IsChecked == true;
    }

    // ══════════════════════════════════════════════════════════════
    //  UPDATE ALERT
    // ══════════════════════════════════════════════════════════════

    private void ShowUpdateAlert(string downloadUrl)
    {
        var alert = new UpdateAlertWindow(downloadUrl);
        alert.Owner = this;
        alert.Show();
    }

    // ══════════════════════════════════════════════════════════════
    //  WINDOW EVENTS
    // ══════════════════════════════════════════════════════════════

    private void Window_StateChanged(object sender, EventArgs e)
    {
        if (WindowState == WindowState.Minimized)
        {
            Hide();
            // Tray icon notification handled by App.xaml.cs
        }
    }

    private void Window_Closing(object sender, System.ComponentModel.CancelEventArgs e)
    {
        // Clean shutdown
        StopOverlay();
        _updater.Dispose();
        _osc.Dispose();
        _pulsoid.Dispose();
        _sharing.Dispose();
        _license.Dispose();
    }
}
