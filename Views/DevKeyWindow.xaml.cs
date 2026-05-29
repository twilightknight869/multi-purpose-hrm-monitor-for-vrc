using System.Windows;
using HRMMonitor.Models;
using HRMMonitor.Services;

namespace HRMMonitor.Views;

public partial class DevKeyWindow : Window
{
    private readonly int    _slot;
    private readonly bool   _hwidLocked;
    private readonly bool   _needsPasswordSet;
    private readonly DevKeyManager.DevKeyResult _reason;
    private readonly System.Action _onSuccess;

    public DevKeyWindow(int slot, bool hwidLocked,
        DevKeyManager.DevKeyResult reason, System.Action onSuccess)
    {
        InitializeComponent();

        _slot            = slot;
        _hwidLocked      = hwidLocked;
        _reason          = reason;
        _onSuccess       = onSuccess;
        _needsPasswordSet = !DevKeyManager.HasPassword(slot);

        SlotLbl.Text = $"Dev Key Slot {slot}  —  " +
                       (hwidLocked ? "HWID Locked" : "Standard");

        // Show username field for slots 4-6
        if (DevKeyManager.NeedsUsername(slot))
        {
            UnameLabel.Visibility = Visibility.Visible;
            UnameBox.Visibility   = Visibility.Visible;
            UnameHint.Visibility  = Visibility.Visible;
            UnameBox.Text = DevKeyManager.GetUsername(slot);
        }

        ConfigureForReason(reason);
    }

    private void ConfigureForReason(DevKeyManager.DevKeyResult reason)
    {
        switch (reason)
        {
            case DevKeyManager.DevKeyResult.PasswordRequired:
                PwLabel.Text       = "CREATE YOUR PASSWORD (set only once)";
                PwConfirmLabel.Visibility  = Visibility.Visible;
                PwConfirmBox.Visibility    = Visibility.Visible;
                StatusLbl.Text     = "First activation — choose a password for this dev key. You cannot change it later.";
                if (_hwidLocked) ShowHwidSection();
                break;

            case DevKeyManager.DevKeyResult.PasswordWrong:
                PwLabel.Text   = "ENTER PASSWORD";
                StatusLbl.Text = "Wrong password. Try again.";
                StatusLbl.Foreground = System.Windows.Media.Brushes.OrangeRed;
                break;

            case DevKeyManager.DevKeyResult.HwidNotBound:
                PwLabel.Text   = "ENTER PASSWORD";
                StatusLbl.Text = "This machine will be permanently bound to your dev key after activation.";
                ShowHwidSection();
                break;

            case DevKeyManager.DevKeyResult.HwidMismatch:
                PwLabel.Text       = "ACCESS DENIED";
                PwBox.IsEnabled    = false;
                ConfirmBtn.IsEnabled = false;
                StatusLbl.Text     = "This dev key is locked to a different machine.";
                StatusLbl.Foreground = System.Windows.Media.Brushes.OrangeRed;
                break;
        }
    }

    private void ShowHwidSection()
    {
        HwidSection.Visibility = Visibility.Visible;
        // Show a masked HWID so the user knows what machine is being locked
        var machineGuid = Microsoft.Win32.Registry.LocalMachine
            .OpenSubKey(@"SOFTWARE\Microsoft\Cryptography")
            ?.GetValue("MachineGuid") as string ?? "unknown";
        HwidLbl.Text = $"Machine: {Environment.MachineName}\nID: {machineGuid[..16]}…";
    }

    private async void ConfirmBtn_Click(object sender, RoutedEventArgs e)
    {
        ConfirmBtn.IsEnabled = false;

        var pw = PwBox.Password;

        if (_needsPasswordSet)
        {
            // Validate confirmation
            if (pw != PwConfirmBox.Password)
            {
                StatusLbl.Text = "Passwords do not match.";
                StatusLbl.Foreground = System.Windows.Media.Brushes.OrangeRed;
                ConfirmBtn.IsEnabled = true;
                return;
            }
            if (pw.Length < 6)
            {
                StatusLbl.Text = "Password must be at least 6 characters.";
                StatusLbl.Foreground = System.Windows.Media.Brushes.OrangeRed;
                ConfirmBtn.IsEnabled = true;
                return;
            }

            // Set the password (one-time)
            if (!DevKeyManager.SetPassword(_slot, pw))
            {
                StatusLbl.Text = "Password already set — use your existing password.";
                StatusLbl.Foreground = System.Windows.Media.Brushes.OrangeRed;
                ConfirmBtn.IsEnabled = true;
                return;
            }
        }

        // Verify password
        AppSettings.Instance.DevPassword = pw;

        // Save custom username (slots 4-6)
        if (DevKeyManager.NeedsUsername(_slot) && !string.IsNullOrWhiteSpace(UnameBox.Text))
            DevKeyManager.SetUsername(_slot, UnameBox.Text);

        // Bind HWID if first use on this machine
        if (_hwidLocked && !DevKeyManager.HasHwid(_slot))
            DevKeyManager.BindHwid(_slot);

        // Re-validate
        var result = DevKeyManager.Validate(
            AppSettings.Instance.LicenseKey, pw, out _);

        // Clear password from memory
        AppSettings.Instance.DevPassword = "";

        if (result == DevKeyManager.DevKeyResult.Valid)
        {
            _onSuccess();
            Close();
        }
        else
        {
            StatusLbl.Text = $"Activation failed: {result}";
            StatusLbl.Foreground = System.Windows.Media.Brushes.OrangeRed;
            ConfirmBtn.IsEnabled = true;
        }
    }

    private void CancelBtn_Click(object sender, RoutedEventArgs e) => Close();
}
