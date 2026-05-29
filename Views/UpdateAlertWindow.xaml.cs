using System.Diagnostics;
using System.Windows;
using System.Windows.Threading;

namespace HRMMonitor.Views;

public partial class UpdateAlertWindow : Window
{
    private readonly string         _downloadUrl;
    private readonly DispatcherTimer _timer = new() { Interval = TimeSpan.FromSeconds(1) };
    private int _secondsLeft = 10;

    public UpdateAlertWindow(string downloadUrl)
    {
        InitializeComponent();
        _downloadUrl = downloadUrl;

        _timer.Tick += Timer_Tick;
        _timer.Start();
    }

    private void Timer_Tick(object? sender, EventArgs e)
    {
        _secondsLeft--;
        CountdownLbl.Text = _secondsLeft > 0
            ? $"Opening browser in {_secondsLeft} s…"
            : "Opening…";

        if (_secondsLeft <= 0)
            OpenAndClose();
    }

    private void NowBtn_Click(object sender, RoutedEventArgs e)  => OpenAndClose();
    private void SkipBtn_Click(object sender, RoutedEventArgs e) => Close();

    private void OpenAndClose()
    {
        _timer.Stop();
        try
        {
            // Open the GitHub releases page in the default browser
            var uri = _downloadUrl.Contains("github.com")
                ? _downloadUrl.Replace("zipball_url", "html_url")
                : _downloadUrl;

            // Fallback: always navigate to releases page
            var releasesUrl = "https://github.com/twilightknight869/Multi-Purpose-HRM-Monitor-For-VRC/releases/latest";
            Process.Start(new ProcessStartInfo(releasesUrl) { UseShellExecute = true });
        }
        catch { /* browser launch error — ignore */ }
        Close();
    }

    protected override void OnClosed(EventArgs e)
    {
        _timer.Stop();
        base.OnClosed(e);
    }
}
