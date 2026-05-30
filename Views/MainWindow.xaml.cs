using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;
using HRMMonitor.Models;
using HRMMonitor.Services;

namespace HRMMonitor.Views;

internal static class StringExt
{
    public static string Truncate(this string s, int max) =>
        s.Length <= max ? s : s[..max] + "…";
}

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
        // Reset old plain templates to the new pretty default
        if (t == "{icon} {bpm} BPM [{bar}]" || t == "{icon} {bpm} BPM  [{bar}]" ||
            (t.Contains("{track}") && !t.Contains("\n")))
        {
            AppSettings.Instance.ChatboxTemplate = "{icon} {bpm} BPM  ( {tier} )\n[{bar}]{track}";
        }
    }

    // ── Load saved settings into controls ─────────────────────────
    private void LoadSettings()
    {
        _suppressChanges = true;
        var s = AppSettings.Instance;

        // Token
        TokenBox.Password   = s.PulsoidToken;
        InvisibleChatboxCheck.IsChecked = s.InvisibleChatbox;
        UnicodeEmojiCheck.IsChecked     = s.UnicodeEmojiMode;

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
        SteamVrCheck.IsChecked      = s.SteamVrEnabled;
        VrRaiseToViewCheck.IsChecked = s.VrRaiseToView;
        VrLeftHand.IsChecked        = s.VrHand != "Right";
        VrRightHand.IsChecked       = s.VrHand == "Right";
        VrSizeSlider.Value          = s.VrOverlaySize;
        VrSizeLbl.Text              = $"{(int)(s.VrOverlaySize * 100)}cm";

        // Settings tab
        BpmHighBox.Text = s.BpmHigh.ToString();
        BpmMedBox.Text  = s.BpmMed.ToString();
        OpacitySlider.Value = s.OverlayOpacity;
        OpacityLbl.Text     = $"{s.OverlayOpacity:P0}";
        ShakeCheck.IsChecked = s.ShakeEnabled;
        SoundCheck.IsChecked = s.HeartbeatSoundEnabled;

        // License
        LicenseKeyBox.Text     = s.LicenseKey;
        DevTagCheck.IsChecked  = s.ShowDevTag;

        // Theme/accent
        ThemeDark.IsChecked   = s.Theme == "Dark";
        ThemeDarker.IsChecked = s.Theme == "Darker";
        ThemeOled.IsChecked   = s.Theme == "OLED";
        ApplyAccent(s.AccentColor);
        ApplyTheme(s.Theme);

        // Pronoun
        foreach (System.Windows.Controls.ComboBoxItem item in PronounBox.Items)
            if (item.Content.ToString() == s.Pronoun) { PronounBox.SelectedItem = item; break; }
        if (PronounBox.SelectedItem == null) PronounBox.SelectedIndex = 0;

        // Viewer
        ViewerCodeBox.Text  = s.ViewerRoomCode;
        GroupCodesBox.Text  = s.GroupRoomCodes.Replace(",", "\n");
        FriendHrOscCheck.IsChecked = s.FriendHrOscEnabled;
        FriendHrParamBox.Text    = s.FriendHrOscParam;

        UpdatePreview();
        _suppressChanges = false;
    }

    // ── Wire service events ───────────────────────────────────────
    private void WireServices()
    {
        // Pulsoid → connection dot + BPM distribution + status panel
        _pulsoid.StatusChanged += status => Dispatcher.Invoke(() =>
        {
            UpdateConnStatus(status);
            SetStatus(StatusPulsoidDot, StatusPulsoidLbl,
                status == "connected" ? "green" : status == "connecting" || status == "reconnecting" ? "orange" : "dim",
                $"Pulsoid: {status}");
        });
        _pulsoid.BpmReceived += bpm => Dispatcher.Invoke(() => OnBpmReceived(bpm));

        // Spotify → chatbox preview + overlay + status panel
        _spotify.StatusChanged += status => Dispatcher.BeginInvoke(() =>
        {
            SetStatus(StatusSpotifyDot, StatusSpotifyLbl,
                status == "connected" ? "blue" : status == "authorizing" ? "orange" : "dim",
                $"Spotify: {status}");
        });
        _spotify.TrackChanged += info => Dispatcher.Invoke(() =>
        {
            _lastTrack  = info?.TrackName  ?? "";
            _lastArtist = info?.ArtistName ?? "";
            UpdatePreview();
            _overlay?.SetTrack(_lastTrack, _lastArtist);
            if (info != null && info.IsPlaying)
                SetStatus(StatusSpotifyDot, StatusSpotifyLbl, "blue", $"Spotify: {_lastTrack}".Truncate(24));
        });

        // SteamVR mode changes
        _steamvr.ModeChanged += mode => Dispatcher.Invoke(() =>
        {
            // Nothing needed in main window — overlay handles its own visibility
        });

        // Update checker
        _updater.UpdateAvailable += url => Dispatcher.Invoke(() => ShowUpdateAlert(url));

        // License — use BeginInvoke so sync code paths don't deadlock the UI thread
        _license.StatusChanged           += s   => Dispatcher.BeginInvoke(() => { UpdateLicenseBadge(s); UpdateStatusPanel(); });
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

        // Tier + icon — Unicode BMP symbols or ASCII fallback
        bool uni = s.UnicodeEmojiMode;
        string tier, icon;
        // Unicode: BMP-only symbols (U+0000–U+FFFF) — VRChat chatbox renders these fine.
        // Complex emoji (💓💗) are outside BMP and show as ? — use ♥ ♡ ❤ instead.
        // ASCII:   safe fallback.
        if (bpm >= high)      { tier = uni ? "HIGH ▲" : "HIGH";  icon = uni ? "❤!!" : "<!>"; }
        else if (bpm >= med)  { tier = uni ? "MED  ~" : "MED";   icon = uni ? "♥~"  : "<3~"; }
        else                  { tier = uni ? "LOW  ▼" : "LOW";   icon = uni ? "♡"   : "<3";  }

        // Prettier progress bar — 12 wide with filled/empty chars
        int filled  = bpm > 0 ? Math.Clamp((int)Math.Round(bpm / 220.0 * 12), 0, 12) : 0;
        string barStr = new string('=', filled) + new string('-', 12 - filled);

        // Track/artist on their own lines with clean prefix
        string trackPfx  = uni ? "♪ " : ">> ";
        string trackVal  = string.IsNullOrEmpty(_lastTrack)  ? "" : $"\n{trackPfx}{_lastTrack}".Truncate(36);
        string artistVal = string.IsNullOrEmpty(_lastArtist) ? "" : $"\n   {_lastArtist}".Truncate(36);

        var msg = s.ChatboxTemplate
            .Replace("{bpm}",     bpm > 0 ? bpm.ToString() : "--")
            .Replace("{bar}",     barStr)
            .Replace("{tier}",    tier)
            .Replace("{icon}",    icon)
            .Replace("{track}",   trackVal)
            .Replace("{artist}",  artistVal)
            .Replace("{pronoun}", s.Pronoun)
            .TrimEnd();

        // Invisible chatbox background (premium/dev only)
        // Prepends invisible Unicode chars that suppress VRChat's grey bubble
        if (s.InvisibleChatbox && _license.IsPremium)
            msg = "​⁣⁤﻿" + msg;

        return msg;
    }

    // ── Generic status dot + label helper ────────────────────────
    private void SetStatus(System.Windows.Shapes.Ellipse dot, TextBlock lbl, string color, string text)
    {
        var fill = color switch
        {
            "green"  => "#FF44cc77",
            "orange" => "#FFffaa33",
            "red"    => "#FFff4444",
            "blue"   => "#FF4488cc",
            _        => "#FF333344",
        };
        dot.Fill = (Brush)new BrushConverter().ConvertFrom(fill)!;
        lbl.Text = text;
        lbl.Foreground = (Brush)new BrushConverter().ConvertFrom(fill)!;
    }

    private void UpdateStatusPanel()
    {
        var s = AppSettings.Instance;
        SetStatus(StatusOscDot,     StatusOscLbl,     _running && s.OscEnabled     ? "blue" : "dim", _running && s.OscEnabled ? "OSC: active"   : "OSC: off");
        SetStatus(StatusChatboxDot, StatusChatboxLbl, _running && s.ChatboxEnabled ? "blue" : "dim", _running && s.ChatboxEnabled ? "Chatbox: on" : "Chatbox: off");
        SetStatus(StatusSharingDot, StatusSharingLbl, _running && s.SharingEnabled ? "green": "dim", _running && s.SharingEnabled ? "Sharing: on" : "Sharing: off");
        SetStatus(StatusLicenseDot, StatusLicenseLbl,
            _license.IsPremium ? "green" : "blue",
            _license.IsPremium ? (_license.ActiveDevSlot > 0 ? $"Dev: {DevKeyManager.GetUsername(_license.ActiveDevSlot)}" : "Premium") : "Free tier");
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

    private void UnicodeEmoji_Changed(object sender, RoutedEventArgs e)
    {
        if (_suppressChanges) return;
        AppSettings.Instance.UnicodeEmojiMode = UnicodeEmojiCheck.IsChecked == true;
        UpdatePreview();
    }

    private void InvisibleChatbox_Changed(object sender, RoutedEventArgs e)
    {
        if (_suppressChanges) return;
        AppSettings.Instance.InvisibleChatbox = InvisibleChatboxCheck.IsChecked == true;
        UpdatePreview();
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

    private void VrRaiseToView_Changed(object sender, RoutedEventArgs e)
    {
        if (_suppressChanges) return;
        AppSettings.Instance.VrRaiseToView = VrRaiseToViewCheck.IsChecked == true;
    }

    private void VrHand_Changed(object sender, RoutedEventArgs e)
    {
        if (_suppressChanges) return;
        var hand = VrRightHand.IsChecked == true ? "Right" : "Left";
        _steamvr.SetHand(hand);
    }

    private void VrSize_Changed(object sender, RoutedPropertyChangedEventArgs<double> e)
    {
        if (_suppressChanges) return;
        var val = (float)VrSizeSlider.Value;
        AppSettings.Instance.VrOverlaySize = val;
        VrSizeLbl.Text = $"{(int)(val * 100)}cm";
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
        UpdateStatusPanel();

        // Start services
        _osc.UpdateTarget(s.OscIp, s.OscPort);
        _pulsoid.Start(s.PulsoidToken);

        if (s.SteamVrEnabled)
            _steamvr.Start();

        if (s.SpotifyEnabled)
        {
            // Try restoring saved token first — only do full auth if that fails
            _ = Task.Run(async () =>
            {
                var restored = await _spotify.TryRestoreAsync(s.SpotifyClientId, s.SpotifyClientSecret);
                if (!restored)
                    await _spotify.AuthorizeAsync(s.SpotifyClientId, s.SpotifyClientSecret, s.SpotifyRedirectUri);
                _spotify.StartPolling();
            });
        }

        // Open overlay
        _overlay = new OverlayWindow();
        _overlay.Opacity = s.OverlayOpacity;
        _overlay.Show();

        // Apply sound setting
        _overlay.SetSoundEnabled(s.HeartbeatSoundEnabled);

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
        UpdateStatusPanel();

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

    private void GroupCodes_Changed(object sender, TextChangedEventArgs e)
    {
        if (_suppressChanges) return;
        AppSettings.Instance.GroupRoomCodes = GroupCodesBox.Text
            .Replace("\r\n", ",").Replace("\n", ",").Trim(',');
    }

    private void WatchGroup_Click(object sender, RoutedEventArgs e)
    {
        var codes = GroupCodesBox.Text
            .Split(new[] { '\n', '\r', ',' }, StringSplitOptions.RemoveEmptyEntries)
            .Select(c => c.Trim().ToUpperInvariant())
            .Where(c => c.Length == 6)
            .Take(5)
            .ToList();

        if (!codes.Any())
        {
            MessageBox.Show("Enter at least one 6-character room code.", "Group Watch",
                MessageBoxButton.OK, MessageBoxImage.Warning);
            return;
        }

        AppSettings.Instance.GroupRoomCodes = string.Join(",", codes);

        // Open a viewer window for each friend — they report BPM to the VR panel
        _steamvr.ClearGroupBpms();
        foreach (var code in codes)
        {
            var win = new ViewerWindow(code, _osc,
                onGroupBpm: (c, b) => _steamvr.SetGroupBpm(c, b));
            win.Show();
        }
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
            var val = item.Content.ToString() ?? "My";
            // For neopronouns like "Xe/Xem", store the full string but use first part in chatbox
            AppSettings.Instance.Pronoun = val;
            UpdatePreview();
        }
    }

    // ── License handlers ──────────────────────────────────────────
    // ── Help tab buttons ─────────────────────────────────────────
    private void ViewSource_Click(object sender, RoutedEventArgs e) =>
        System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(
            "https://github.com/twilightknight869/Multi-Purpose-HRM-Monitor-For-VRC/tree/v2")
            { UseShellExecute = true });

    private void VirusTotal_Click(object sender, RoutedEventArgs e) =>
        System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(
            "https://www.virustotal.com/gui/home/upload")
            { UseShellExecute = true });

    // ── UI Customization ──────────────────────────────────────────
    private void Accent_Click(object sender, RoutedEventArgs e)
    {
        if (sender is not System.Windows.Controls.Button btn) return;
        var color = btn.Tag?.ToString() ?? "#FFe03535";
        AppSettings.Instance.AccentColor = color;
        ApplyAccent(color);
    }

    private void Theme_Changed(object sender, RoutedEventArgs e)
    {
        if (_suppressChanges) return;
        var theme = ThemeOled.IsChecked == true ? "OLED" :
                    ThemeDarker.IsChecked == true ? "Darker" : "Dark";
        AppSettings.Instance.Theme = theme;
        ApplyTheme(theme);
    }

    private void ApplyAccent(string hex)
    {
        try
        {
            var brush = (Brush)new BrushConverter().ConvertFrom(hex)!;
            // Update accent resources app-wide
            Application.Current.Resources["AccentBrush"] = brush;
            var color = ((SolidColorBrush)brush).Color;
            Application.Current.Resources["AccentColor"] = color;

            // Update preview text
            AccentPreview.Foreground = brush;
            AppSettings.Instance.AccentColor = hex;
        }
        catch { }
    }

    private void ApplyTheme(string theme)
    {
        var (bg, surface) = theme switch
        {
            "OLED"   => ("#FF000000", "#FF0a0a0a"),
            "Darker" => ("#FF080810", "#FF0f0f1a"),
            _        => ("#FF0f0f18", "#FF1a1a28"),
        };
        try
        {
            Application.Current.Resources["BgBrush"]      = new SolidColorBrush((Color)ColorConverter.ConvertFromString(bg)!);
            Application.Current.Resources["SurfaceBrush"] = new SolidColorBrush((Color)ColorConverter.ConvertFromString(surface)!);
            Application.Current.Resources["BgColor"]      = (Color)ColorConverter.ConvertFromString(bg)!;
            Application.Current.Resources["SurfaceColor"] = (Color)ColorConverter.ConvertFromString(surface)!;
        }
        catch { }
    }

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
            FreeTimeLbl.Visibility           = Visibility.Collapsed;
            InvisibleChatboxCheck.Visibility  = Visibility.Visible;
            CustomizeGroup.Visibility         = Visibility.Visible;
            if (_license.ActiveDevSlot >= 1 && _license.ActiveDevSlot <= 3)
                DevTagCheck.Visibility = Visibility.Visible;
        }
        else
        {
            DevTagCheck.Visibility            = Visibility.Collapsed;
            InvisibleChatboxCheck.Visibility  = Visibility.Collapsed;
            CustomizeGroup.Visibility         = Visibility.Collapsed;
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

    private void SoundCheck_Changed(object sender, RoutedEventArgs e)
    {
        if (_suppressChanges) return;
        var on = SoundCheck.IsChecked == true;
        AppSettings.Instance.HeartbeatSoundEnabled = on;
        // Apply live to running overlay
        _overlay?.SetSoundEnabled(on);
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
