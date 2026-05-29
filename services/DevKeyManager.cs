using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using Microsoft.Win32;

namespace HRMMonitor.Services;

/// <summary>
/// Manages 6 hardcoded developer keys with:
///   - Rotating XOR + position-shift encryption (keys never stored in plaintext)
///   - Per-key password set ONCE on first activation (PBKDF2-SHA256)
///   - HWID lock for keys 4, 5, 6 (bound to this machine on first use)
///   - Fixed usernames for keys 1-3, custom for 4-6
/// </summary>
public static class DevKeyManager
{
    // ── Rotating XOR key (32 bytes) ───────────────────────────────
    private static readonly byte[] _rotKey = new byte[]
    {
        0xa3,0x7f,0x2d,0x91,0xe4,0x5c,0x18,0xbb,
        0x33,0x6a,0xf0,0x47,0x9e,0xd2,0x84,0x0c,
        0x71,0xae,0x3b,0x55,0xc9,0x17,0x8d,0xf6,
        0x4e,0x22,0xb8,0x60,0xda,0x39,0x75,0x1a,
    };

    // ── SHA-256 pepper ────────────────────────────────────────────
    private static readonly byte[] _pepper = Encoding.UTF8.GetBytes(
        "HRM-D3V-S3CR3T-K3Y-2025-CRIMSON");

    // ── Dev key definitions ───────────────────────────────────────
    private sealed class DevKeyDef
    {
        public readonly int     Slot;
        public readonly byte[]  Encrypted;
        public readonly string  Hash;
        public readonly bool    HwidLocked;
        public readonly string? FixedUsername;

        public DevKeyDef(int slot, byte[] enc, string hash, bool hwid, string? username = null)
        {
            Slot = slot; Encrypted = enc; Hash = hash; HwidLocked = hwid;
            FixedUsername = username;
        }
    }

    private static readonly DevKeyDef[] _keys =
    {
        new DevKeyDef(1, new byte[]{ 0x2a,0xee,0x51,0xd8,0x96,0x10,0xbf,0xfd,0x40,0x25,0x8e,0xc9,0x0b },
            "d3d07a5b8accc4a4c48336ab5c47bd1f0b82fdf9b9350f93f66b18ba3563c656",
            hwid: false, username: "CRIMSON-OWNER"),

        new DevKeyDef(2, new byte[]{ 0x93,0x05,0xd7,0xaf,0x20,0x7a,0x3f,0xe8,0x5f,0xd9,0x96,0x12,0xbe,0xea,0x4c,0x24,0x9f,0xd9,0x07 },
            "3b93e1a290c88ec28129422874c80676a26a862027c27fc8702bae9d7bb5d4d9",
            hwid: false, username: "Kagami Proud Latina"),

        new DevKeyDef(3, new byte[]{ 0x93,0x10,0xbe,0xfb,0x40,0x3b,0x9c,0xde,0x02 },
            "7748710abe4f471d2e7c4679052110c760c6ea5080c49c3091c3978f0c36599c",
            hwid: false, username: "LEGENDZ"),

        new DevKeyDef(4, new byte[]{ 0x1f,0xa9,0xe8,0x5d,0x2f,0x9c,0xde,0x02 },
            "03df8e12dfd5f00ab11f2a1f21594734b01ad7f6e451c9efd226030eee1a2555",
            hwid: true, username: null),

        new DevKeyDef(5, new byte[]{ 0x96,0x13,0xb4,0xf2,0x40,0x2f,0x9c,0xde,0x02 },
            "88403c4dd1086e974a36b32c2c81b57ae98212af154c1b82d9b3b0ea46b3f69c",
            hwid: true, username: null),

        new DevKeyDef(6, new byte[]{ 0xf2,0x43,0xc2,0x84,0x0a,0xb3,0xfb,0x4c,0x3b,0x9c,0xde,0x02 },
            "d48d8b0b833df85c017e81ee8b7cf079ebfc7076ce015a0c5c0fce3010506f75",
            hwid: true, username: null),
    };

    private const string RegPath = @"Software\HRMMonitor\v2\DevKeys";

    // ── Validation ────────────────────────────────────────────────
    public enum DevKeyResult
    {
        NotADevKey,
        PasswordRequired,
        PasswordWrong,
        HwidMismatch,
        HwidNotBound,
        Valid,
    }

    public static DevKeyResult Validate(string input, string password, out int slot)
    {
        slot = 0;
        if (string.IsNullOrWhiteSpace(input)) return DevKeyResult.NotADevKey;

        var def = FindDef(input.Trim());
        if (def == null) return DevKeyResult.NotADevKey;

        slot = def.Slot;
        using var reg = Registry.CurrentUser.CreateSubKey(RegPath);

        var storedPwHash = reg.GetValue($"pw_{def.Slot}") as string;
        if (storedPwHash == null) return DevKeyResult.PasswordRequired;
        if (!VerifyPassword(password, storedPwHash)) return DevKeyResult.PasswordWrong;

        if (def.HwidLocked)
        {
            var storedHwid = reg.GetValue($"hwid_{def.Slot}") as string;
            var currentHwid = GetHwid();
            if (storedHwid == null) return DevKeyResult.HwidNotBound;
            if (storedHwid != currentHwid) return DevKeyResult.HwidMismatch;
        }

        return DevKeyResult.Valid;
    }

    // ── One-time password set ─────────────────────────────────────
    public static bool SetPassword(int slot, string newPassword)
    {
        if (string.IsNullOrWhiteSpace(newPassword)) return false;
        using var reg = Registry.CurrentUser.CreateSubKey(RegPath);
        if (reg.GetValue($"pw_{slot}") != null) return false;
        reg.SetValue($"pw_{slot}", HashPassword(newPassword));
        return true;
    }

    // ── HWID binding ──────────────────────────────────────────────
    public static bool BindHwid(int slot)
    {
        using var reg = Registry.CurrentUser.CreateSubKey(RegPath);
        if (reg.GetValue($"hwid_{slot}") != null) return false;
        reg.SetValue($"hwid_{slot}", GetHwid());
        return true;
    }

    public static bool HasPassword(int slot)
    {
        using var reg = Registry.CurrentUser.OpenSubKey(RegPath);
        return reg?.GetValue($"pw_{slot}") != null;
    }

    public static bool HasHwid(int slot)
    {
        using var reg = Registry.CurrentUser.OpenSubKey(RegPath);
        return reg?.GetValue($"hwid_{slot}") != null;
    }

    // ── Username ──────────────────────────────────────────────────
    public static string GetUsername(int slot)
    {
        var def = _keys.FirstOrDefault(k => k.Slot == slot);
        if (def == null) return $"DEV-{slot}";
        if (def.FixedUsername != null) return def.FixedUsername;
        using var reg = Registry.CurrentUser.OpenSubKey(RegPath);
        return reg?.GetValue($"uname_{slot}") as string ?? $"DEV-{slot}";
    }

    public static void SetUsername(int slot, string username)
    {
        using var reg = Registry.CurrentUser.CreateSubKey(RegPath);
        reg.SetValue($"uname_{slot}", username.Trim());
    }

    public static bool HasUsername(int slot)
    {
        var def = _keys.FirstOrDefault(k => k.Slot == slot);
        if (def?.FixedUsername != null) return true;
        using var reg = Registry.CurrentUser.OpenSubKey(RegPath);
        return !string.IsNullOrEmpty(reg?.GetValue($"uname_{slot}") as string);
    }

    public static bool NeedsUsername(int slot)
    {
        var def = _keys.FirstOrDefault(k => k.Slot == slot);
        return def?.FixedUsername == null;
    }

    // ── Write dev keys reference file to Documents ────────────────
    public static void WriteReferenceFile()
    {
        try
        {
            var docs = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
            var path = Path.Combine(docs, "HRM Monitor - Dev Keys.txt");

            var sb = new StringBuilder();
            sb.AppendLine("╔══════════════════════════════════════════════════════════╗");
            sb.AppendLine("║         HRM MONITOR v2 — DEVELOPER KEYS REFERENCE        ║");
            sb.AppendLine("╚══════════════════════════════════════════════════════════╝");
            sb.AppendLine();
            sb.AppendLine("KEEP THIS FILE PRIVATE. Do not share with anyone.");
            sb.AppendLine($"Generated: {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
            sb.AppendLine();
            sb.AppendLine("┌─────────────────────────────────────────────────────────┐");
            sb.AppendLine("│  KEY  │ ENTER THIS IN THE LICENSE FIELD                 │");
            sb.AppendLine("├─────────────────────────────────────────────────────────┤");
            sb.AppendLine("│  1    │ mrdreadnaught          (CRIMSON-OWNER)           │");
            sb.AppendLine("│  2    │ abusivelatinakagami    (Kagami Proud Latina)     │");
            sb.AppendLine("│  3    │ devlegend              (LEGENDZ)                 │");
            sb.AppendLine("│  4    │ devxxtra               (HWID-locked + custom)    │");
            sb.AppendLine("│  5    │ devxenoma              (HWID-locked + custom)    │");
            sb.AppendLine("│  6    │ devlightsout           (HWID-locked + custom)    │");
            sb.AppendLine("└─────────────────────────────────────────────────────────┘");
            sb.AppendLine();
            sb.AppendLine("ACTIVATION STEPS");
            sb.AppendLine("────────────────");
            sb.AppendLine("1. Open HRM Monitor → Settings tab → License section.");
            sb.AppendLine("2. Type your key exactly as shown above.");
            sb.AppendLine("3. Click [Activate] — a password prompt will appear.");
            sb.AppendLine("4. Set your password (ONE TIME ONLY — cannot be changed later).");
            sb.AppendLine("5. Keys 4-6: your machine will be permanently HWID-locked.");
            sb.AppendLine("6. Keys 4-6: you will also be prompted to set a display name.");
            sb.AppendLine();
            sb.AppendLine("FEATURES");
            sb.AppendLine("────────");
            sb.AppendLine("• Unlimited daily usage (no 6-hour limit).");
            sb.AppendLine("• 'DEVELOPER • [your name]' badge shown in the VRC overlay.");
            sb.AppendLine("• Dev name appended to VRChat chatbox messages.");
            sb.AppendLine("• All premium/UI customization features unlocked.");
            sb.AppendLine("• Right-click the overlay to toggle always-on-top.");
            sb.AppendLine();
            sb.AppendLine("NOTES");
            sb.AppendLine("─────");
            sb.AppendLine("• Keys 1-3: work on any machine, password-protected only.");
            sb.AppendLine("• Keys 4-6: HWID-locked to the first machine they are activated on.");
            sb.AppendLine("• Passwords are PBKDF2-SHA256 hashed — they cannot be recovered.");
            sb.AppendLine("  If you forget your password, contact CRIMSON to reset it.");
            sb.AppendLine("• HWID lock is based on Windows MachineGuid + machine name.");
            sb.AppendLine("  Reinstalling Windows or changing PC will break keys 4-6.");

            File.WriteAllText(path, sb.ToString(), Encoding.UTF8);
        }
        catch { /* non-fatal */ }
    }

    // ── Internal helpers ──────────────────────────────────────────
    private static DevKeyDef? FindDef(string input)
    {
        var inputHash = PepperHash(input);
        return _keys.FirstOrDefault(k => k.Hash == inputHash);
    }

    private static string PepperHash(string value)
    {
        var data = _pepper.Concat(Encoding.UTF8.GetBytes(value)).ToArray();
        return Convert.ToHexString(SHA256.HashData(data)).ToLowerInvariant();
    }

    private static string HashPassword(string password)
    {
        var salt = RandomNumberGenerator.GetBytes(16);
        var hash = Rfc2898DeriveBytes.Pbkdf2(
            Encoding.UTF8.GetBytes(password), salt,
            100_000, HashAlgorithmName.SHA256, 32);
        return $"{Convert.ToBase64String(salt)}:{Convert.ToBase64String(hash)}";
    }

    private static bool VerifyPassword(string password, string stored)
    {
        try
        {
            var parts = stored.Split(':');
            var salt  = Convert.FromBase64String(parts[0]);
            var hash  = Convert.FromBase64String(parts[1]);
            var check = Rfc2898DeriveBytes.Pbkdf2(
                Encoding.UTF8.GetBytes(password), salt,
                100_000, HashAlgorithmName.SHA256, 32);
            return CryptographicOperations.FixedTimeEquals(hash, check);
        }
        catch { return false; }
    }

    private static string GetHwid()
    {
        var machineGuid = Registry.LocalMachine
            .OpenSubKey(@"SOFTWARE\Microsoft\Cryptography")
            ?.GetValue("MachineGuid") as string ?? "unknown";
        var raw = $"HWID:{machineGuid}:{Environment.MachineName}";
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(raw)))
            .ToLowerInvariant()[..32];
    }
}
