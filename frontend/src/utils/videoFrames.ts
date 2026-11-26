/**
 * Client-side HTML5 video poster & keyframe fallback extractor.
 * Extracts duration-adaptive JPEG frames when backend transcode/ffmpeg extraction is unavailable.
 */
function computeBrowserFrameCount(durSec: number): number {
  if (!durSec || durSec <= 0) return 6;
  if (durSec <= 6) return 6;
  if (durSec <= 20) return 10;
  if (durSec <= 45) return 14;
  return 18;
}

export async function extractVideoFramesAndPoster(
  file: File,
  maxFrames?: number
): Promise<{ poster: string; frames: string[]; durationSec: number }> {
  const url = URL.createObjectURL(file);
  const video = document.createElement("video");
  video.muted = true;
  video.playsInline = true;
  video.preload = "auto";
  video.src = url;
  try {
    video.load();
  } catch {}

  const frames: string[] = [];
  let poster = "";
  let durationSec = 0;

  try {
    await new Promise<void>((resolve, reject) => {
      const timer = window.setTimeout(() => reject(new Error("video metadata timeout")), 12000);
      video.onloadeddata = () => {
        window.clearTimeout(timer);
        resolve();
      };
      video.onerror = () => {
        window.clearTimeout(timer);
        reject(new Error("video decode failed"));
      };
    });

    const dur = Number.isFinite(video.duration) && video.duration > 0 ? video.duration : 0;
    durationSec = Math.round(dur);
    const frameTarget = maxFrames ?? computeBrowserFrameCount(dur);
    const vw = video.videoWidth || 640;
    const vh = video.videoHeight || 360;
    const maxDim = frameTarget > 12 ? 512 : 640;
    const scale = Math.min(1, maxDim / Math.max(vw, vh));
    const cw = Math.max(2, Math.round(vw * scale));
    const ch = Math.max(2, Math.round(vh * scale));

    const canvas = document.createElement("canvas");
    canvas.width = cw;
    canvas.height = ch;
    const ctx = canvas.getContext("2d");
    if (!ctx) return { poster: "", frames: [], durationSec };

    const sampleTimes =
      dur > 0.4
        ? Array.from({ length: frameTarget }, (_, idx) => {
            const frac = (idx + 0.5) / frameTarget;
            return Math.min(Math.max(0.05, dur * frac), Math.max(0.05, dur - 0.05));
          })
        : [0];

    for (const t of sampleTimes) {
      if (t > 0 && Math.abs(video.currentTime - t) > 0.03) {
        await new Promise<void>((resolve) => {
          const timer = window.setTimeout(resolve, 1400);
          const onSeeked = () => {
            window.clearTimeout(timer);
            video.removeEventListener("seeked", onSeeked);
            resolve();
          };
          video.addEventListener("seeked", onSeeked);
          try {
            video.currentTime = t;
          } catch {
            window.clearTimeout(timer);
            video.removeEventListener("seeked", onSeeked);
            resolve();
          }
        });
      }
      ctx.drawImage(video, 0, 0, cw, ch);
      const dataUrl = canvas.toDataURL("image/jpeg", 0.74);
      if (dataUrl && dataUrl.startsWith("data:image/")) {
        if (!poster) poster = dataUrl;
        frames.push(dataUrl);
      }
    }
  } catch {
    // Backend ffmpeg processor will automatically transcode and extract frames & audio on upload
  } finally {
    URL.revokeObjectURL(url);
  }

  return { poster, frames, durationSec };
}
