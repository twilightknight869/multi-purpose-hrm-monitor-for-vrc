using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using HRMMonitor.Models;
#if OPENVR
using Valve.VR;
#endif

namespace HRMMonitor.Services;

/// <summary>
/// Apple Watch-style wrist overlay for SteamVR/OpenVR.
/// Anchors to the selected hand controller, raise-to-view support,
/// and a secondary info panel that expands when the wrist is raised.
/// </summary>
public class SteamVrService : IDisposable
{
    public event Action<string>? ModeChanged;

    private int    _lastBpm;
    private string _lastStatus = "LOW";

    // Group BPMs: code → bpm
    private readonly Dictionary<string, int> _groupBpms = new();
    public void SetGroupBpm(string roomCode, int bpm) => _groupBpms[roomCode] = bpm;
    public void ClearGroupBpms() => _groupBpms.Clear();

    public void SetBpm(int bpm)
    {
        _lastBpm = bpm;
        _lastStatus = bpm >= AppSettings.Instance.BpmHigh ? "HIGH" :
                      bpm >= AppSettings.Instance.BpmMed  ? "MED"  : "LOW";
    }

#if OPENVR
    // ── Watch overlay constants ────────────────────────────────────
    private const string WatchKey    = "hrm_wrist_watch";
    private const string WatchName   = "HRM Monitor";
    private const string PanelKey    = "hrm_wrist_panel";
    private const string PanelName   = "HRM Info";

    // ── State ──────────────────────────────────────────────────────
    private CVRSystem?  _vr;
    private CVROverlay? _overlay;
    private ulong _watchHandle = OpenVR.k_ulOverlayHandleInvalid;
    private ulong _panelHandle = OpenVR.k_ulOverlayHandleInvalid;
    private bool  _vrRunning;
    private CancellationTokenSource _cts = new();
    private uint  _handIndex = OpenVR.k_unTrackedDeviceIndexInvalid;

    // ── Wrist transform matrices ──────────────────────────────────
    // HmdMatrix34_t is row-major: [m0..m3] = row0 (right), [m4..m7] = row1 (up), [m8..m11] = row2 (fwd)
    // Positions are in metres relative to the controller grip origin.
    private static HmdMatrix34_t WristMatrix(bool leftHand)
    {
        // For wrist overlay (Apple Watch): sits on back of hand.
        // When controller is held naturally: +Y is up, +Z is toward the user.
        // We want the overlay face pointing "outward" from the wrist.
        float side = leftHand ? 1f : -1f;
        return new HmdMatrix34_t
        {
            // Row 0 – right vector (along hand width)
            m0 = side, m1 = 0f,   m2 = 0f,   m3 = 0f,
            // Row 1 – up vector (away from back of hand)
            m4 = 0f,   m5 = 0f,   m6 = -1f,  m7 = 0.06f,   // 6 cm above grip = wrist
            // Row 2 – forward vector (along fingers)
            m8 = 0f,   m9 = 1f,   m10 = 0f,  m11 = -0.04f, // 4 cm toward fingers
        };
    }

    private static HmdMatrix34_t PanelMatrix(bool leftHand)
    {
        // Info panel: floats 30 cm in front of the wrist when raised
        float side = leftHand ? 1f : -1f;
        return new HmdMatrix34_t
        {
            m0 = side, m1 = 0f,  m2 = 0f,  m3 = 0f,
            m4 = 0f,   m5 = 1f,  m6 = 0f,  m7 = 0.15f,   // 15 cm above grip
            m8 = 0f,   m9 = 0f,  m10 = 1f, m11 = -0.30f, // 30 cm in front
        };
    }

    // ── Start / Stop ──────────────────────────────────────────────
    public void Start()
    {
        _cts = new CancellationTokenSource();
        _ = Task.Run(PollLoop, _cts.Token);
    }

    private async Task PollLoop()
    {
        while (!_cts.IsCancellationRequested)
        {
            bool running = IsSteamVrRunning();

            if (running && !_vrRunning)
            {
                _vrRunning = true;
                InitOverlays();
                ModeChanged?.Invoke("vr");
            }
            else if (!running && _vrRunning)
            {
                _vrRunning = false;
                ShutdownOverlays();
                ModeChanged?.Invoke("desktop");
            }

            if (_vrRunning)
            {
                UpdateHandTracking();
                RenderWatch();
                HandleRaiseToView();
            }

            await Task.Delay(100, _cts.Token).ContinueWith(_ => { });
        }
    }

    private static bool IsSteamVrRunning()
    {
        try { return Process.GetProcessesByName("vrserver").Length > 0; }
        catch { return false; }
    }

    // ── Init ──────────────────────────────────────────────────────
    private void InitOverlays()
    {
        try
        {
            var err = EVRInitError.None;
            _vr = OpenVR.Init(ref err, EVRApplicationType.VRApplication_Overlay);
            if (err != EVRInitError.None || _vr == null) { _vr = null; return; }

            _overlay = OpenVR.Overlay;

            // Watch overlay
            _overlay.CreateOverlay(WatchKey, WatchName, ref _watchHandle);
            float size = AppSettings.Instance.VrOverlaySize;
            _overlay.SetOverlayWidthInMeters(_watchHandle, size);
            _overlay.SetOverlayAlpha(_watchHandle, 1.0f);
            _overlay.ShowOverlay(_watchHandle);

            // Panel overlay (larger info display)
            _overlay.CreateOverlay(PanelKey, PanelName, ref _panelHandle);
            _overlay.SetOverlayWidthInMeters(_panelHandle, size * 3f);
            _overlay.SetOverlayAlpha(_panelHandle, 0f); // hidden until wrist raised
        }
        catch { _vr = null; }
    }

    // ── Hand tracking ─────────────────────────────────────────────
    private void UpdateHandTracking()
    {
        if (_overlay == null || _vr == null) return;
        try
        {
            var s        = AppSettings.Instance;
            bool isLeft  = s.VrHand != "Right";
            var role     = isLeft ? ETrackedControllerRole.LeftHand : ETrackedControllerRole.RightHand;
            uint idx     = _vr.GetTrackedDeviceIndexForControllerRole(role);

            if (idx == OpenVR.k_unTrackedDeviceIndexInvalid) return;
            _handIndex = idx;

            var wristMat = WristMatrix(isLeft);
            _overlay.SetOverlayTransformTrackedDeviceRelative(_watchHandle, idx, ref wristMat);

            var panelMat = PanelMatrix(isLeft);
            _overlay.SetOverlayTransformTrackedDeviceRelative(_panelHandle, idx, ref panelMat);
        }
        catch { }
    }

    // ── Raise-to-view ─────────────────────────────────────────────
    private void HandleRaiseToView()
    {
        if (!AppSettings.Instance.VrRaiseToView || _overlay == null || _vr == null) return;
        if (_handIndex == OpenVR.k_unTrackedDeviceIndexInvalid) return;
        try
        {
            var poses = new TrackedDevicePose_t[OpenVR.k_unMaxTrackedDeviceCount];
            _vr.GetDeviceToAbsoluteTrackingPose(ETrackingUniverseOrigin.TrackingUniverseStanding, 0, poses);

            var pose = poses[_handIndex];
            if (!pose.bPoseIsValid) return;

            // Extract the "up" vector of the hand (row 1 of the 3x4 matrix)
            var m  = pose.mDeviceToAbsoluteTracking;
            float uy = m.m5; // Y component of hand's up vector in world space

            // Wrist raised = hand's up vector pointing upward (uy > 0.5)
            bool raised = uy > 0.5f;

            // Show/hide panel based on raise state
            _overlay.SetOverlayAlpha(_panelHandle, raised ? 0.95f : 0f);
            if (raised) RenderPanel();
        }
        catch { }
    }

    // ── Render watch face ─────────────────────────────────────────
    private void RenderWatch()
    {
        if (_overlay == null || _watchHandle == OpenVR.k_ulOverlayHandleInvalid) return;
        try
        {
            const int size = 256;
            using var bmp = new Bitmap(size, size, PixelFormat.Format32bppArgb);
            using var g   = Graphics.FromImage(bmp);
            g.SmoothingMode     = SmoothingMode.AntiAlias;
            g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.AntiAlias;

            // Watch face background — circular, dark
            using var bgBrush = new SolidBrush(Color.FromArgb(230, 10, 10, 20));
            g.FillEllipse(bgBrush, 4, 4, size - 8, size - 8);

            // Coloured border ring based on BPM tier
            var tierColor = _lastStatus == "HIGH" ? Color.FromArgb(255, 80, 40) :
                            _lastStatus == "MED"  ? Color.FromArgb(255, 170, 51) :
                                                    Color.FromArgb(68, 204, 119);
            using var borderPen = new Pen(tierColor, 8f);
            g.DrawEllipse(borderPen, 4, 4, size - 8, size - 8);

            // BPM number — large, centred
            var bpmText  = _lastBpm > 0 ? _lastBpm.ToString() : "--";
            using var bpmFont = new Font("Segoe UI", _lastBpm > 99 ? 52 : 62, FontStyle.Bold);
            using var bpmBrush = new SolidBrush(Color.White);
            var bpmSize   = g.MeasureString(bpmText, bpmFont);
            g.DrawString(bpmText, bpmFont, bpmBrush,
                (size - bpmSize.Width) / 2f, (size - bpmSize.Height) / 2f - 8f);

            // "BPM" label below
            using var lblFont  = new Font("Segoe UI", 14, FontStyle.Regular);
            using var lblBrush = new SolidBrush(Color.FromArgb(180, 200, 200, 200));
            var lblSize = g.MeasureString("BPM", lblFont);
            g.DrawString("BPM", lblFont, lblBrush,
                (size - lblSize.Width) / 2f, size / 2f + 42f);

            // Tier label at top
            using var tierFont  = new Font("Segoe UI", 12, FontStyle.Bold);
            using var tierBrush = new SolidBrush(tierColor);
            var tierSize = g.MeasureString(_lastStatus, tierFont);
            g.DrawString(_lastStatus, tierFont, tierBrush,
                (size - tierSize.Width) / 2f, 22f);

            UploadTexture(_watchHandle, bmp, size);
        }
        catch { }
    }

    // ── Render info panel (shown when wrist raised) ───────────────
    private void RenderPanel()
    {
        if (_overlay == null || _panelHandle == OpenVR.k_ulOverlayHandleInvalid) return;
        try
        {
            const int w = 512, h = 256;
            using var bmp = new Bitmap(w, h, PixelFormat.Format32bppArgb);
            using var g   = Graphics.FromImage(bmp);
            g.SmoothingMode = SmoothingMode.AntiAlias;

            // Dark rounded background
            using var bgBrush = new SolidBrush(Color.FromArgb(220, 10, 10, 20));
            using var path    = RoundedRect(new RectangleF(4, 4, w - 8, h - 8), 20);
            g.FillPath(bgBrush, path);

            var accent = _lastStatus == "HIGH" ? Color.FromArgb(255, 80, 40) :
                         _lastStatus == "MED"  ? Color.FromArgb(255, 170, 51) :
                                                 Color.FromArgb(68, 204, 119);

            using var borderPen = new Pen(accent, 3f);
            g.DrawPath(borderPen, path);

            // Large BPM
            var bpmText = _lastBpm > 0 ? _lastBpm.ToString() : "--";
            using var bpmFont  = new Font("Segoe UI", 72, FontStyle.Bold);
            using var bpmBrush = new SolidBrush(Color.White);
            g.DrawString(bpmText, bpmFont, bpmBrush, 20f, 30f);

            // Status column
            using var subFont  = new Font("Segoe UI", 16, FontStyle.Regular);
            using var subBrush = new SolidBrush(Color.FromArgb(200, 200, 200));
            using var accBrush = new SolidBrush(accent);

            g.DrawString("BPM", subFont, subBrush, 22f, 175f);
            g.DrawString(_lastStatus, subFont, accBrush, 100f, 175f);

            // Group BPMs — horror game friend list
            var s   = AppSettings.Instance;
            float gy = 60f;
            if (_groupBpms.Any())
            {
                g.DrawString("FRIENDS", subFont, subBrush, 260f, gy); gy += 28f;
                foreach (var (code, fbpm) in _groupBpms.Take(5))
                {
                    var fc = fbpm >= s.BpmHigh ? Color.FromArgb(255, 80, 40) :
                             fbpm >= s.BpmMed  ? Color.FromArgb(255, 170, 51) :
                                                 Color.FromArgb(68, 204, 119);
                    using var fb = new SolidBrush(fc);
                    g.DrawString($"{code}: {fbpm} BPM", subFont, fb, 260f, gy);
                    gy += 28f;
                }
            }
            else
            {
                g.DrawString($"Room: {s.RoomCode}", subFont, subBrush, 260f, 60f);
                g.DrawString($"Hand: {s.VrHand}", subFont, subBrush, 260f, 88f);
            }

            UploadTexture(_panelHandle, bmp, w);
        }
        catch { }
    }

    private static GraphicsPath RoundedRect(RectangleF bounds, float radius)
    {
        var path = new GraphicsPath();
        path.AddArc(bounds.X, bounds.Y, radius * 2, radius * 2, 180, 90);
        path.AddArc(bounds.Right - radius * 2, bounds.Y, radius * 2, radius * 2, 270, 90);
        path.AddArc(bounds.Right - radius * 2, bounds.Bottom - radius * 2, radius * 2, radius * 2, 0, 90);
        path.AddArc(bounds.X, bounds.Bottom - radius * 2, radius * 2, radius * 2, 90, 90);
        path.CloseFigure();
        return path;
    }

    // ── Texture upload ─────────────────────────────────────────────
    private void UploadTexture(ulong handle, Bitmap bmp, int size)
    {
        var bits = bmp.LockBits(
            new Rectangle(0, 0, bmp.Width, bmp.Height),
            ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
        try
        {
            var tex = new Texture_t
            {
                handle      = bits.Scan0,
                eType       = ETextureType.DirectX,
                eColorSpace = EColorSpace.Auto,
            };
            _overlay?.SetOverlayTexture(handle, ref tex);
        }
        finally { bmp.UnlockBits(bits); }
    }

    // ── Shutdown ──────────────────────────────────────────────────
    private void ShutdownOverlays()
    {
        if (_vr == null) return;
        try
        {
            if (_watchHandle != OpenVR.k_ulOverlayHandleInvalid)
                _overlay?.DestroyOverlay(_watchHandle);
            if (_panelHandle != OpenVR.k_ulOverlayHandleInvalid)
                _overlay?.DestroyOverlay(_panelHandle);
        }
        catch { }
        finally
        {
            _watchHandle = OpenVR.k_ulOverlayHandleInvalid;
            _panelHandle = OpenVR.k_ulOverlayHandleInvalid;
            try { OpenVR.Shutdown(); } catch { }
            _vr = null; _overlay = null;
        }
    }

    // ── Hand switching (can be called live) ───────────────────────
    public void SetHand(string hand)
    {
        AppSettings.Instance.VrHand = hand;
        // Next UpdateHandTracking call picks it up automatically
    }

    public void Stop() { _cts.Cancel(); ShutdownOverlays(); }
    public void Dispose() => Stop();

#else
    public void Start()  { }
    public void Stop()   { }
    public void SetHand(string hand) { }
    public void Dispose(){ }
#endif
}
