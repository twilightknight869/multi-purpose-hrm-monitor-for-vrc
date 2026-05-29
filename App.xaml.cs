using System.Linq;
using System.Windows;
using HRMMonitor.Services;
using System.Windows.Controls;
using System.Windows.Media;
using Hardcodet.Wpf.TaskbarNotification;
using HRMMonitor.Views;

namespace HRMMonitor;

public partial class App : Application
{
    private TaskbarIcon? _trayIcon;
    private MainWindow?  _mainWindow;

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        // Catch any unhandled exception and show it rather than silently dying
        DispatcherUnhandledException += (_, ex) =>
        {
            MessageBox.Show(ex.Exception.ToString(), "HRM Monitor — Startup Error",
                MessageBoxButton.OK, MessageBoxImage.Error);
            ex.Handled = true;
            Shutdown(1);
        };

        // Keep running when all windows are closed (lives in system tray)
        ShutdownMode = ShutdownMode.OnExplicitShutdown;

        try
        {
            _trayIcon = (TaskbarIcon)FindResource("TrayIcon");

            // Wire context menu in code — XAML routing is unreliable for tray icons
            var menuBg   = new SolidColorBrush(Color.FromRgb(0x0f, 0x0f, 0x18));
            var menuFg   = new SolidColorBrush(Color.FromRgb(0xe0, 0xe0, 0xe0));
            var hoverBg  = new SolidColorBrush(Color.FromRgb(0xe0, 0x35, 0x35));

            MenuItem MakeItem(string header)
            {
                var item = new MenuItem
                {
                    Header     = header,
                    Background = menuBg,
                    Foreground = menuFg,
                    FontFamily = new System.Windows.Media.FontFamily("Segoe UI"),
                    FontSize   = 13,
                };
                item.MouseEnter += (s, _) => ((MenuItem)s).Background = hoverBg;
                item.MouseLeave += (s, _) => ((MenuItem)s).Background = menuBg;
                return item;
            }

            var openItem = MakeItem("Open HRM Monitor");
            openItem.Click += (_, _) => TrayOpen_Click(this, new RoutedEventArgs());

            var exitItem = MakeItem("Exit");
            exitItem.Click += (_, _) => TrayExit_Click(this, new RoutedEventArgs());

            _trayIcon.ContextMenu = new ContextMenu
            {
                Background  = menuBg,
                BorderBrush = new SolidColorBrush(Color.FromRgb(0x2e, 0x2e, 0x48)),
                BorderThickness = new Thickness(1),
                Items = { openItem, new Separator(), exitItem }
            };

            // Double-click also opens
            _trayIcon.TrayMouseDoubleClick += (_, _) => TrayOpen_Click(this, new RoutedEventArgs());
        }
        catch (Exception ex)
        {
            MessageBox.Show($"Tray icon failed to load:\n{ex.Message}\n\nThe app will run without a tray icon.",
                "HRM Monitor", MessageBoxButton.OK, MessageBoxImage.Warning);
        }

        // Write dev keys reference file to Documents (owner only sees this)
        DevKeyManager.WriteReferenceFile();

        // Show splash → then main window
        var splash = new SplashWindow();
        splash.Completed += OnSplashCompleted;
        splash.Show();
    }

    private void OnSplashCompleted()
    {
        try
        {
            _mainWindow = new MainWindow();
            _mainWindow.Show();
        }
        catch (Exception ex)
        {
            MessageBox.Show($"Failed to open main window:\n\n{ex}", "HRM Monitor — Error",
                MessageBoxButton.OK, MessageBoxImage.Error);
            Shutdown(1);
        }
    }

    private void TrayOpen_Click(object sender, RoutedEventArgs e)
    {
        if (_mainWindow == null)
            _mainWindow = new MainWindow();

        _mainWindow.Show();
        _mainWindow.Activate();
        _mainWindow.WindowState = WindowState.Normal;
    }

    private void TrayExit_Click(object sender, RoutedEventArgs e)
    {
        // Close the context menu before disposing — otherwise it lingers on screen
        if (_trayIcon?.ContextMenu != null)
            _trayIcon.ContextMenu.IsOpen = false;

        _trayIcon?.Dispose();
        _trayIcon = null;

        // Close MainWindow first — its Window_Closing handler stops the overlay,
        // viewer windows, and all services cleanly.
        if (_mainWindow != null)
        {
            _mainWindow.Show();   // must be visible for Close() to fire Closing event
            _mainWindow.Close();
        }

        // Force-close any remaining windows (viewer overlays, update alerts, etc.)
        foreach (Window w in Windows.Cast<Window>().ToList())
            try { w.Close(); } catch { }

        Shutdown();
    }

    protected override void OnExit(ExitEventArgs e)
    {
        _trayIcon?.Dispose();
        base.OnExit(e);
    }
}
