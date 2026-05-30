using System.Windows;
using System.Windows.Controls;
using Hardcodet.Wpf.TaskbarNotification;
using HRMMonitor.Services;
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

            // Use system-styled menu — custom WPF colours fight Windows 11's tray chrome
            var openItem = new MenuItem { Header = "Open HRM Monitor" };
            openItem.Click += (_, _) => TrayOpen_Click(this, new RoutedEventArgs());

            var exitItem = new MenuItem { Header = "Exit" };
            exitItem.Click += (_, _) => TrayExit_Click(this, new RoutedEventArgs());

            _trayIcon.ContextMenu = new ContextMenu
            {
                Items = { openItem, new Separator(), exitItem }
            };

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
        // Dismiss the context menu first
        if (_trayIcon?.ContextMenu != null)
            _trayIcon.ContextMenu.IsOpen = false;

        // Dispose tray icon so it vanishes from the taskbar immediately
        _trayIcon?.Dispose();
        _trayIcon = null;

        // Close main window through its own Closing handler (stops overlay, services, etc.)
        // Make it visible first so the Closing event fires properly
        if (_mainWindow != null)
        {
            _mainWindow.Show();
            _mainWindow.Close();
        }

        // Hard shutdown — kills any remaining windows
        Environment.Exit(0);
    }

    protected override void OnExit(ExitEventArgs e)
    {
        _trayIcon?.Dispose();
        base.OnExit(e);
    }
}
