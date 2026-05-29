using System.Diagnostics;
#if OPENVR
using Valve.VR;
#endif

namespace HRMMonitor.Services;

/// <summary>
/// Polls every 5 s for vrserver.exe.  When SteamVR is running, opens
/// an OpenVR wrist overlay and renders the current BPM onto it.
/// Fires ModeChanged("vr") / ModeChanged("desktop") as VR starts/stops.
///
/// Requires openvr_api.cs (downloaded by build.bat).
/// When that file is absent the service compiles as a harmless no-op stub.
/// </summary>
public class SteamVrService : IDisposable
{
    public event Action<string>? ModeChanged;   // "vr" | "desktop"

    private int  _lastBpm;
    public  void SetBpm(int bpm) => _lastBpm = bpm;

#if OPENVR
    // ── Full OpenVR implementation ─────────────────────────────────
    private const string OverlayKey   = "hrm_monitor_v2_overlay";
    private const string OverlayName  = "HRM Monitor";
    private const float  OverlayWidth = 0.12f;   // metres

    private CVRSystem?  _vrSystem;
    private CVROverlay? _vrOverlay;
    private ulong       _overlayHandle = OpenVR.k_ulOverlayHandleInvalid;
    private bool        _vrRunning;
    private CancellationTokenSource _cts = new();

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
                TryInitOverlay();
                ModeChanged?.Invoke("vr");
            }
            else if (!running && _vrRunning)
            {
                _vrRunning = false;
                ShutdownOverlay();
                ModeChanged?.Invoke("desktop");
            }

            if (_vrRunning && _overlayHandle != OpenVR.k_ulOverlayHandleInvalid)
                RenderBpm(_lastBpm);

            await Task.Delay(5000, _cts.Token).ContinueWith(_ => { });
        }
    }

    private static bool IsSteamVrRunning()
    {
        try { return Process.GetProcessesByName("vrserver").Length > 0; }
        catch { return false; }
    }

    private void TryInitOverlay()
    {
        try
        {
            var err = EVRInitError.None;
            _vrSystem  = OpenVR.Init(ref err, EVRApplicationType.VRApplication_Overlay);
            if (err != EVRInitError.None) { _vrSystem = null; return; }
            _vrOverlay = OpenVR.Overlay;
            _vrOverlay.CreateOverlay(OverlayKey, OverlayName, ref _overlayHandle);
            _vrOverlay.SetOverlayWidthInMeters(_overlayHandle, OverlayWidth);
            _vrOverlay.ShowOverlay(_overlayHandle);
        }
        catch { _vrSystem = null; }
    }

    private void ShutdownOverlay()
    {
        // Only touch the native DLL if we actually initialized it.
        // Calling OpenVR.Shutdown() when the DLL was never loaded throws DllNotFoundException.
        if (_vrSystem == null)
        {
            _overlayHandle = OpenVR.k_ulOverlayHandleInvalid;
            return;
        }
        try
        {
            if (_overlayHandle != OpenVR.k_ulOverlayHandleInvalid)
                _vrOverlay?.DestroyOverlay(_overlayHandle);
        }
        catch { }
        finally
        {
            _overlayHandle = OpenVR.k_ulOverlayHandleInvalid;
            try { OpenVR.Shutdown(); } catch { }
            _vrSystem  = null;
            _vrOverlay = null;
        }
    }

    private void RenderBpm(int bpm)
    {
        try
        {
            const int size = 256;
            using var bmp  = new System.Drawing.Bitmap(size, size);
            using var g    = System.Drawing.Graphics.FromImage(bmp);
            g.Clear(System.Drawing.Color.FromArgb(200, 10, 0, 0));
            using var font  = new System.Drawing.Font("Consolas", 48, System.Drawing.FontStyle.Bold);
            using var brush = new System.Drawing.SolidBrush(
                bpm >= 140 ? System.Drawing.Color.Red :
                bpm >= 100 ? System.Drawing.Color.Orange :
                             System.Drawing.Color.LimeGreen);
            var text = bpm > 0 ? bpm.ToString() : "--";
            var sf   = new System.Drawing.StringFormat
            {
                Alignment     = System.Drawing.StringAlignment.Center,
                LineAlignment = System.Drawing.StringAlignment.Center,
            };
            g.DrawString(text, font, brush, new System.Drawing.RectangleF(0, 0, size, size), sf);

            var bits = bmp.LockBits(
                new System.Drawing.Rectangle(0, 0, size, size),
                System.Drawing.Imaging.ImageLockMode.ReadOnly,
                System.Drawing.Imaging.PixelFormat.Format32bppArgb);

            var tex = new Texture_t
            {
                handle      = bits.Scan0,
                eType       = ETextureType.DirectX,
                eColorSpace = EColorSpace.Auto,
            };
            _vrOverlay?.SetOverlayTexture(_overlayHandle, ref tex);
            bmp.UnlockBits(bits);
        }
        catch { /* non-fatal */ }
    }

    public void Stop()
    {
        _cts.Cancel();
        ShutdownOverlay();
    }

    public void Dispose() => Stop();

#else
    // ── Stub when openvr_api.cs was not downloaded ─────────────────
    public void Start()  { /* SteamVR not available — no-op */ }
    public void Stop()   { /* no-op */ }
    public void Dispose(){ /* no-op */ }
#endif
}
