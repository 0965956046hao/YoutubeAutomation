"use client";

import { useEffect, useState } from "react";
import { checkFacebookPage, disconnectAuth, getAuthUrl, getConfig, saveConfig } from "@/lib/api";

export default function ConfigPanel({ onSaved }: { onSaved: () => void }) {
  const [clientId, setClientId] = useState("");
  const [secret, setSecret] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [geminiKey, setGeminiKey] = useState("");
  const [redirectUri, setRedirectUri] = useState("");
  const [channelsText, setChannelsText] = useState("");
  const [days, setDays] = useState(2);
  const [connected, setConnected] = useState(false);
  const [channelTitle, setChannelTitle] = useState("");
  const [hasSecret, setHasSecret] = useState(false);
  const [hasKey, setHasKey] = useState(false);
  const [hasGemini, setHasGemini] = useState(false);
  const [msg, setMsg] = useState("");
  const [saving, setSaving] = useState(false);
  const [facebookPageId, setFacebookPageId] = useState("");
  const [facebookToken, setFacebookToken] = useState("");
  const [facebookVersion, setFacebookVersion] = useState("v25.0");
  const [hasFacebookToken, setHasFacebookToken] = useState(false);
  const [checkingFacebook, setCheckingFacebook] = useState(false);

  async function load() {
    try {
      const cfg = await getConfig();
      setClientId(cfg.youtube_client_id);
      setRedirectUri(cfg.oauth_redirect_uri);
      setChannelsText(cfg.track_channel_ids.join("\n"));
      setDays(cfg.days_window);
      setConnected(cfg.connected);
      setChannelTitle(cfg.channel_title);
      setHasSecret(cfg.has_client_secret);
      setHasKey(cfg.has_api_key);
      setHasGemini(cfg.has_gemini_key);
      setFacebookPageId(cfg.facebook_page_id);
      setHasFacebookToken(cfg.has_facebook_token);
      setFacebookVersion(cfg.facebook_api_version);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Không tải được cấu hình");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleSave() {
    setSaving(true);
    setMsg("");
    try {
      await saveConfig({
        youtube_client_id: clientId.trim(),
        ...(secret.trim() ? { youtube_client_secret: secret.trim() } : {}),
        ...(apiKey.trim() ? { youtube_api_key: apiKey.trim() } : {}),
        ...(geminiKey.trim() ? { gemini_api_key: geminiKey.trim() } : {}),
        oauth_redirect_uri: redirectUri.trim(),
        track_channel_ids: channelsText
          .split(/[\n,]+/)
          .map((s) => s.trim())
          .filter(Boolean),
        days_window: days,
        facebook_page_id: facebookPageId.trim(),
        facebook_api_version: facebookVersion.trim(),
        ...(facebookToken.trim() ? { facebook_page_token: facebookToken.trim() } : {}),
      });
      setSecret("");
      setApiKey("");
      setGeminiKey("");
      setFacebookToken("");
      setMsg("Đã lưu cấu hình.");
      onSaved();
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Lưu thất bại");
    } finally {
      setSaving(false);
    }
  }

  async function handleConnect() {
    try {
      const url = await getAuthUrl();
      window.location.href = url;
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Không tạo được URL login");
    }
  }

  return (
    <div className="double-bezel animate-fade-up">
      <div className="double-bezel-inner p-6">
        <span className="eyebrow">Cấu hình YouTube API</span>
        <h2 className="mt-3 text-xl font-semibold">Kết nối &amp; kênh theo dõi</h2>
        <p className="mt-1 text-[13px] text-ink-muted">
          OAuth 2.0 là bắt buộc để upload / sửa mô tả / đăng. API key chỉ là
          fallback đọc public khi chưa login.
        </p>

        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <label className="block">
            <span className="mb-1.5 block text-[12px] font-medium text-ink-muted">Client ID</span>
            <input className="input-field" value={clientId} onChange={(e) => setClientId(e.target.value)} placeholder="xxx.apps.googleusercontent.com" />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-[12px] font-medium text-ink-muted">
              Client Secret {hasSecret && <span className="tag ml-2">đã lưu</span>}
            </span>
            <input className="input-field" type="password" value={secret} onChange={(e) => setSecret(e.target.value)} placeholder={hasSecret ? "Để trống = giữ nguyên" : "GOCSPX-..."} />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-[12px] font-medium text-ink-muted">
              API key (optional) {hasKey && <span className="tag ml-2">đã lưu</span>}
            </span>
            <input className="input-field" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="AIza..." />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-[12px] font-medium text-ink-muted">
              Gemini API key {hasGemini && <span className="tag ml-2">đã lưu</span>}
            </span>
            <input className="input-field" type="password" value={geminiKey} onChange={(e) => setGeminiKey(e.target.value)} placeholder={hasGemini ? "Để trống = giữ nguyên" : "AIza... (lấy ở aistudio.google.com)"} />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-[12px] font-medium text-ink-muted">Redirect URI</span>
            <input className="input-field font-mono !text-[12px]" value={redirectUri} onChange={(e) => setRedirectUri(e.target.value)} placeholder="http://localhost:8001/api/youtube/auth/callback" />
          </label>
        </div>

        <div className="mt-4 grid gap-4 md:grid-cols-[1fr_140px]">
          <label className="block">
            <span className="mb-1.5 block text-[12px] font-medium text-ink-muted">
              Kênh theo dõi — mỗi dòng 1 channel ID (UC...) hoặc handle (@tenkenh)
            </span>
            <textarea className="textarea-field !font-sans !text-[13px]" rows={4} value={channelsText} onChange={(e) => setChannelsText(e.target.value)} placeholder={"UCxxxx...\n@tenkenh"} />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-[12px] font-medium text-ink-muted">Số ngày</span>
            <input className="input-field" type="number" min={1} max={7} value={days} onChange={(e) => setDays(Math.min(7, Math.max(1, Number(e.target.value) || 2)))} />
            <span className="mt-1.5 block text-[11px] text-ink-light">Mặc định 2 ngày</span>
          </label>
        </div>

        <div className="mt-6 border-t border-white/10 pt-5">
          <span className="eyebrow">Facebook Page · video / Reels</span>
          <p className="mt-2 text-[12px] leading-relaxed text-ink-muted">
            Dùng Page access token của Page muốn đăng, với quyền pages_manage_posts và pages_read_engagement.
            Token chỉ lưu ở backend. Lưu cấu hình rồi kiểm tra kết nối.
          </p>
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            <label className="block">
              <span className="mb-1.5 block text-[12px] font-medium text-ink-muted">Facebook Page ID</span>
              <input className="input-field" inputMode="numeric" value={facebookPageId} onChange={(e) => setFacebookPageId(e.target.value)} placeholder="ID dạng số của Page" />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[12px] font-medium text-ink-muted">
                Page access token {hasFacebookToken && <span className="tag ml-2">đã lưu</span>}
              </span>
              <input className="input-field" type="password" autoComplete="new-password" value={facebookToken} onChange={(e) => setFacebookToken(e.target.value)} placeholder={hasFacebookToken ? "Để trống = giữ nguyên" : "Page token của Meta"} />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[12px] font-medium text-ink-muted">Graph API version</span>
              <input className="input-field" value={facebookVersion} onChange={(e) => setFacebookVersion(e.target.value)} placeholder="v25.0" />
            </label>
            <div className="flex items-end">
              <button className="btn-island-secondary btn-sm" disabled={checkingFacebook || saving || !hasFacebookToken} onClick={async () => {
                setCheckingFacebook(true);
                try {
                  const page = await checkFacebookPage();
                  setMsg(`Facebook đã kết nối: ${page.name} (${page.id}).`);
                } catch (e) {
                  setMsg(e instanceof Error ? e.message : "Không kết nối được Facebook.");
                } finally {
                  setCheckingFacebook(false);
                }
              }}>{checkingFacebook ? "Đang kiểm tra…" : "Kiểm tra Page đã lưu"}</button>
            </div>
          </div>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button className="btn-island-primary btn-sm" disabled={saving} onClick={handleSave}>
            {saving ? "Đang lưu…" : "Lưu cấu hình"}
          </button>
          {connected ? (
            <>
              <span className="tag !text-emerald-300 !border-emerald-400/30">
                ● Đã kết nối{channelTitle ? `: ${channelTitle}` : ""}
              </span>
              <button
                className="btn-island-danger btn-sm"
                onClick={async () => {
                  await disconnectAuth();
                  setConnected(false);
                  setChannelTitle("");
                  onSaved();
                }}
              >
                Ngắt kết nối
              </button>
            </>
          ) : (
            <button className="btn-island-secondary btn-sm" onClick={handleConnect}>
              Kết nối Google
            </button>
          )}
        </div>

        {msg && <p className="mt-3 text-[12px] text-ink-muted">{msg}</p>}
      </div>
    </div>
  );
}
