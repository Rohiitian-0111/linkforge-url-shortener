import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { ApiError, humanError, loadSession, request, saveSession } from "./api";
import { Icon } from "./icons";
import type { IconName } from "./icons";
import type {
  Analytics,
  AuthResponse,
  Dashboard,
  DailyClicks,
  Link,
  LinkInput,
  LinkList,
  LinkStatus,
  Session,
  User,
} from "./types";
import {
  count,
  displayUrl,
  fullDate,
  hostname,
  linkStatus,
  localDateTime,
  shortDate,
} from "./utils";

function Brand({ inverse = false }: { inverse?: boolean }) {
  return (
    <div className={`brand ${inverse ? "brand-inverse" : ""}`}>
      <span className="brand-mark">
        <Icon name="link" size={23} />
      </span>
      <span>
        linkforge<span className="brand-dot">.</span>
      </span>
    </div>
  );
}

function Spinner() {
  return <span className="spinner" aria-hidden="true" />;
}

function ErrorBanner({
  children,
  onRetry,
}: {
  children: ReactNode;
  onRetry?: () => void;
}) {
  return (
    <div className="error-banner" role="alert">
      <Icon name="warning" size={18} />
      <span>{children}</span>
      {onRetry && (
        <button className="text-button" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

function AuthScreen({
  onLogin,
  notice,
}: {
  onLogin: (session: Session) => void;
  notice: string;
}) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (mode === "register")
        await request<User>("/auth/register", undefined, {
          method: "POST",
          body: JSON.stringify({
            name: name.trim(),
            email: email.trim(),
            password,
          }),
        });
      const result = await request<AuthResponse>("/auth/login", undefined, {
        method: "POST",
        body: JSON.stringify({ email: email.trim(), password }),
      });
      onLogin({
        access_token: result.access_token,
        user: result.user,
        expires_at: Date.now() + result.expires_in * 1000,
      });
    } catch (err) {
      setError(humanError(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth-layout">
      <section className="auth-story">
        <Brand inverse />
        <div className="auth-story-content">
          <div className="eyebrow light">
            <span className="tiny-dot" /> SMALL LINKS. BIG POSSIBILITIES.
          </div>
          <h1>
            A better way
            <br />
            to share what
            <br />
            <em>matters.</em>
          </h1>
          <p>
            Give every destination a memorable link.
            <br />
            Keep everything organized. See what connects.
          </p>
          <div className="link-illustration" aria-hidden="true">
            <div className="link-ring ring-one" />
            <div className="link-ring ring-two" />
            <span className="spark spark-one">✦</span>
            <span className="spark spark-two">✦</span>
          </div>
          <div className="auth-features">
            <span>
              <Icon name="link" size={17} /> Custom short links
            </span>
            <span>
              <Icon name="chart" size={17} /> Click insights
            </span>
            <span>
              <Icon name="shield" size={17} /> Your own workspace
            </span>
          </div>
        </div>
        <div className="auth-story-footer">
          A little less URL. A lot more possibility.
        </div>
      </section>
      <section className="auth-panel">
        <div className="auth-mobile-brand">
          <Brand />
        </div>
        <div className="auth-form-wrap">
          <span className="section-kicker">YOUR LINK WORKSPACE</span>
          <h2>
            {mode === "login" ? "Welcome back." : "Make room for good links."}
          </h2>
          <p className="muted">
            {mode === "login"
              ? "Sign in to pick up where you left off."
              : "Create your account and share your first short link."}
          </p>
          <div className="auth-tabs" role="tablist" aria-label="Account access">
            <button
              role="tab"
              aria-selected={mode === "login"}
              className={mode === "login" ? "selected" : ""}
              onClick={() => {
                setMode("login");
                setError("");
              }}
            >
              Sign in
            </button>
            <button
              role="tab"
              aria-selected={mode === "register"}
              className={mode === "register" ? "selected" : ""}
              onClick={() => {
                setMode("register");
                setError("");
              }}
            >
              Create account
            </button>
          </div>
          {notice && (
            <div className="notice" role="status">
              {notice}
            </div>
          )}
          {error && <ErrorBanner>{error}</ErrorBanner>}
          <form onSubmit={submit} className="auth-form">
            {mode === "register" && (
              <label>
                Your name
                <input
                  autoComplete="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Alex Morgan"
                  required
                  minLength={1}
                  maxLength={80}
                />
              </label>
            )}
            <label>
              Email address
              <input
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                maxLength={254}
              />
            </label>
            <label>
              Password
              <div className="password-field">
                <input
                  type={showPassword ? "text" : "password"}
                  autoComplete={
                    mode === "register" ? "new-password" : "current-password"
                  }
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={
                    mode === "register"
                      ? "At least 10 characters"
                      : "Enter your password"
                  }
                  required
                  minLength={mode === "register" ? 10 : 1}
                  maxLength={128}
                />
                <button
                  type="button"
                  className="icon-button"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                  onClick={() => setShowPassword((value) => !value)}
                >
                  <Icon name="eye" size={18} />
                </button>
              </div>
              {mode === "register" && (
                <span className="field-hint">
                  Use 10–128 characters. A longer passphrase works well.
                </span>
              )}
            </label>
            <button
              className="button primary auth-submit"
              disabled={busy}
              type="submit"
            >
              {busy ? (
                <>
                  <Spinner />{" "}
                  {mode === "login" ? "Signing in…" : "Creating your account…"}
                </>
              ) : (
                <>
                  {mode === "login"
                    ? "Sign in to Linkforge"
                    : "Create your workspace"}
                  <Icon name="arrow" size={18} />
                </>
              )}
            </button>
          </form>
          <p className="auth-footnote">
            <Icon name="shield" size={15} /> Link management and analytics are
            private. Short links are public.
          </p>
        </div>
        <footer className="auth-panel-footer">
          <span>Built for the things you share.</span>
          <a href="/docs" target="_blank" rel="noreferrer">
            Explore the API <Icon name="external" size={13} />
          </a>
        </footer>
      </section>
    </div>
  );
}

function Modal({
  title,
  subtitle,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const frame = requestAnimationFrame(() => {
      const first = ref.current?.querySelector<HTMLElement>(
        'input, select, button:not([aria-label="Close dialog"])',
      );
      (first || ref.current)?.focus();
    });
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeRef.current();
      if (event.key !== "Tab") return;
      const elements = Array.from(
        ref.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), [tabindex="0"]',
        ) || [],
      );
      const first = elements[0],
        last = elements.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", keydown);
    return () => {
      cancelAnimationFrame(frame);
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", keydown);
      previousFocus?.focus();
    };
  }, []);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className={`modal ${wide ? "modal-wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={ref}
        tabIndex={-1}
      >
        <header className="modal-header">
          <div>
            <h2 id={titleId}>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button
            className="icon-button"
            aria-label="Close dialog"
            onClick={onClose}
          >
            <Icon name="close" />
          </button>
        </header>
        {children}
      </div>
    </div>
  );
}

function LinkModal({
  link,
  token,
  onClose,
  onSaved,
}: {
  link: Link | null;
  token: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [url, setUrl] = useState(link?.original_url || "");
  const [title, setTitle] = useState(link?.title || "");
  const [alias, setAlias] = useState("");
  const [expiry, setExpiry] = useState(localDateTime(link?.expires_at || null));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const payload: LinkInput = {
        original_url: url.trim(),
        title: title.trim(),
      };
      // Preserve an unchanged expiry, including on a link that already expired.
      if (!link || expiry !== localDateTime(link.expires_at)) {
        payload.expires_at = expiry ? new Date(expiry).toISOString() : null;
      }
      if (!link && alias.trim()) payload.custom_alias = alias.trim();
      await request<Link>(link ? `/urls/${link.id}` : "/urls", token, {
        method: link ? "PATCH" : "POST",
        body: JSON.stringify(payload),
      });
      onSaved();
    } catch (err) {
      setError(humanError(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={link ? "Edit your link" : "Create a short link"}
      subtitle={
        link
          ? "Update the destination and details. Your short code stays the same."
          : "A long destination. A short, memorable way to get there."
      }
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <form className="modal-form" onSubmit={save}>
        {error && <ErrorBanner>{error}</ErrorBanner>}
        <label>
          Destination URL <span className="required">*</span>
          <input
            type="url"
            placeholder="https://example.com/something-great"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
            maxLength={4096}
          />
          <span className="field-hint">
            A public website starting with https:// or http://.
          </span>
        </label>
        <label>
          Link title <span className="optional">Optional</span>
          <input
            placeholder="e.g. My portfolio"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={160}
          />
        </label>
        {!link ? (
          <label>
            Custom short code <span className="optional">Optional</span>
            <div className="input-prefix">
              <span>/r/</span>
              <input
                placeholder="my-portfolio"
                value={alias}
                onChange={(e) => setAlias(e.target.value)}
                minLength={3}
                maxLength={32}
                pattern="[A-Za-z0-9_-]{3,32}"
                aria-describedby="alias-hint"
              />
            </div>
            <span className="field-hint" id="alias-hint">
              3–32 letters, numbers, hyphens or underscores. Leave blank for a
              random code.
            </span>
          </label>
        ) : (
          <div className="current-short">
            <Icon name="link" size={17} />
            <span>{displayUrl(link.short_url)}</span>
            <span className="small muted">Permanent</span>
          </div>
        )}
        <label>
          Expiration{" "}
          <span className="optional">Optional · your local time</span>
          <input
            type="datetime-local"
            value={expiry}
            onChange={(e) => setExpiry(e.target.value)}
          />
          <span className="field-hint">
            Leave empty to keep this link available indefinitely.
          </span>
        </label>
        <div className="modal-footer">
          <button
            className="button secondary"
            type="button"
            onClick={onClose}
            disabled={busy}
          >
            Cancel
          </button>
          <button className="button primary" disabled={busy} type="submit">
            {busy ? (
              <Spinner />
            ) : (
              <Icon name={link ? "check" : "plus"} size={17} />
            )}
            {busy ? "Saving…" : link ? "Save changes" : "Create link"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function DeleteModal({
  link,
  token,
  onClose,
  onDeleted,
}: {
  link: Link;
  token: string;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function remove() {
    setBusy(true);
    setError("");
    try {
      await request<void>(`/urls/${link.id}`, token, { method: "DELETE" });
      onDeleted();
    } catch (err) {
      setError(humanError(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title="Delete this link?"
      subtitle="This action cannot be undone from your workspace."
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <div className="modal-form">
        {error && <ErrorBanner>{error}</ErrorBanner>}
        <div className="delete-preview">
          <Icon name="link" />
          <strong>{link.title || hostname(link.original_url)}</strong>
          <span>{displayUrl(link.short_url)}</span>
        </div>
        <p className="muted">
          The link will stop redirecting and disappear from your dashboard. Its
          short code stays reserved, so it cannot be claimed by someone else.
        </p>
        <div className="modal-footer">
          <button
            className="button secondary"
            onClick={onClose}
            disabled={busy}
          >
            Keep link
          </button>
          <button className="button danger" onClick={remove} disabled={busy}>
            {busy ? <Spinner /> : <Icon name="trash" size={17} />}
            {busy ? "Deleting…" : "Delete link"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

function ActivityChart({
  data,
  compact = false,
}: {
  data: DailyClicks[];
  compact?: boolean;
}) {
  const width = 680,
    height = 210,
    left = 40,
    right = 14,
    top = 17,
    bottom = 30;
  const plotHeight = height - top - bottom,
    plotWidth = width - left - right;
  const largest = Math.max(4, ...data.map((point) => point.clicks));
  const max = Math.ceil(largest / 4) * 4;
  const x = (index: number) =>
    left + (index / Math.max(data.length - 1, 1)) * plotWidth;
  const y = (value: number) => top + plotHeight - (value / max) * plotHeight;
  const line = data
    .map(
      (point, index) =>
        `${index === 0 ? "M" : "L"}${x(index)},${y(point.clicks)}`,
    )
    .join(" ");
  const area = data.length
    ? `${line} L${x(data.length - 1)},${top + plotHeight} L${left},${top + plotHeight} Z`
    : "";
  const gradientId = useId().replace(/:/g, "");
  const nonzero = data.some((point) => point.clicks > 0);
  const indexes = data.length
    ? [
        ...new Set([
          0,
          Math.floor((data.length - 1) / 3),
          Math.floor(((data.length - 1) * 2) / 3),
          data.length - 1,
        ]),
      ]
    : [];
  return (
    <div className={`activity-chart ${compact ? "compact" : ""}`}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`Daily clicks, ${count(data.reduce((total, point) => total + point.clicks, 0))} total for the selected period`}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#1c8b68" stopOpacity=".2" />
            <stop offset="100%" stopColor="#1c8b68" stopOpacity=".015" />
          </linearGradient>
        </defs>
        {[0, 1, 2, 3, 4].map((tick) => (
          <g key={tick}>
            <line
              x1={left}
              x2={width - right}
              y1={y((max / 4) * tick)}
              y2={y((max / 4) * tick)}
              stroke="#e9eeeb"
              strokeDasharray="3 4"
            />
            <text
              x={left - 11}
              y={y((max / 4) * tick) + 4}
              textAnchor="end"
              className="chart-tick"
            >
              {count((max / 4) * tick)}
            </text>
          </g>
        ))}
        {area && <path d={area} fill={`url(#${gradientId})`} />}
        {line && (
          <path
            d={line}
            fill="none"
            stroke="#18855f"
            strokeWidth="2.7"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        )}
        {data.length <= 7 &&
          data.map((point, index) => (
            <circle
              key={point.date}
              cx={x(index)}
              cy={y(point.clicks)}
              r="3"
              fill="#fff"
              stroke="#18855f"
              strokeWidth="2"
            >
              <title>
                {point.date}: {count(point.clicks)} clicks
              </title>
            </circle>
          ))}
        {indexes.map((index) => (
          <text
            key={index}
            x={x(index)}
            y={height - 6}
            textAnchor={
              index === 0
                ? "start"
                : index === data.length - 1
                  ? "end"
                  : "middle"
            }
            className="chart-tick"
          >
            {shortDate(`${data[index].date}T12:00:00Z`)}
          </text>
        ))}
      </svg>
      {!nonzero && (
        <div className="chart-empty">
          <Icon name="cursor" size={19} />
          <span>Share a link to see your first clicks.</span>
        </div>
      )}
    </div>
  );
}

function Breakdown({
  title,
  items,
  empty,
}: {
  title: string;
  items: { label: string; clicks: number }[];
  empty: string;
}) {
  const total = items.reduce((sum, item) => sum + item.clicks, 0);
  return (
    <section className="breakdown">
      <h3>{title}</h3>
      {items.length === 0 ? (
        <p className="muted small">{empty}</p>
      ) : (
        items.map((item) => (
          <div className="breakdown-item" key={item.label}>
            <div>
              <span title={item.label}>{item.label || "Direct / unknown"}</span>
              <strong>{count(item.clicks)}</strong>
            </div>
            <div className="breakdown-track">
              <span
                style={{ width: `${total ? (item.clicks / total) * 100 : 0}%` }}
              />
            </div>
          </div>
        ))
      )}
    </section>
  );
}

function AnalyticsModal({
  link,
  token,
  onClose,
}: {
  link: Link;
  token: string;
  onClose: () => void;
}) {
  const [days, setDays] = useState(30);
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    request<Analytics>(`/urls/${link.id}/analytics?days=${days}`, token, {
      signal: controller.signal,
    })
      .then(setData)
      .catch((err) => {
        if (!controller.signal.aborted) setError(humanError(err));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [link.id, days, token, revision]);
  useEffect(() => {
    const interval = setInterval(
      () => setRevision((value) => value + 1),
      15_000,
    );
    return () => clearInterval(interval);
  }, []);
  return (
    <Modal
      title={link.title || "Link insights"}
      subtitle={displayUrl(link.short_url)}
      onClose={onClose}
      wide
    >
      <div className="analytics-body">
        <div className="analytics-toolbar">
          <span className="live-note">
            <span className="tiny-dot" /> Updates every 15 seconds
          </span>
          <label className="sr-only" htmlFor="analytics-days">
            Analytics period
          </label>
          <select
            id="analytics-days"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          >
            {[7, 30, 90].map((value) => (
              <option key={value} value={value}>
                Last {value} days
              </option>
            ))}
          </select>
        </div>
        {error && (
          <ErrorBanner onRetry={() => setRevision((value) => value + 1)}>
            {error}
          </ErrorBanner>
        )}
        {loading && !data ? (
          <div className="loading-block">
            <Spinner /> Loading your insights…
          </div>
        ) : (
          data && (
            <>
              <div className="analytics-stats">
                <div>
                  <span>All-time clicks</span>
                  <strong>{count(data.total_clicks)}</strong>
                </div>
                <div>
                  <span>Last {days} days</span>
                  <strong>{count(data.period_clicks)}</strong>
                </div>
              </div>
              <ActivityChart data={data.clicks_by_day} compact />
              <div className="breakdown-grid">
                <Breakdown
                  title="Top referrers"
                  items={data.referrers.map((item) => ({
                    label: item.referrer,
                    clicks: item.clicks,
                  }))}
                  empty="Referrers will appear after your link is visited."
                />
                <Breakdown
                  title="Devices"
                  items={data.devices.map((item) => ({
                    label: item.device,
                    clicks: item.clicks,
                  }))}
                  empty="Device categories will appear after your first click."
                />
              </div>
              <p className="analytics-note">
                Counts are visits, including repeats and bots, not unique
                people. Day boundaries use UTC. Referrers may be hidden by the
                visitor’s browser.
              </p>
            </>
          )
        )}
      </div>
    </Modal>
  );
}

function StatCard({
  label,
  value,
  detail,
  icon,
  tone = "",
}: {
  label: string;
  value: number | undefined;
  detail: string;
  icon: IconName;
  tone?: string;
}) {
  return (
    <div className={`stat-card ${tone}`}>
      <div className="stat-card-top">
        <span>{label}</span>
        <span className="stat-icon">
          <Icon name={icon} size={19} />
        </span>
      </div>
      <strong>{value === undefined ? "—" : count(value)}</strong>
      <div className="stat-card-detail">{detail}</div>
    </div>
  );
}

function StatusBadge({ link }: { link: Link }) {
  const status = linkStatus(link);
  return (
    <span
      className={`status-badge ${status}`}
      title={
        link.expires_at ? `Expires ${fullDate(link.expires_at)}` : undefined
      }
    >
      <span />
      {status === "inactive"
        ? "Paused"
        : status === "expired"
          ? "Expired"
          : "Active"}
    </span>
  );
}

function LinkTable({
  links,
  total,
  page,
  pageSize,
  loading,
  search,
  status,
  onPage,
  onCreate,
  onEdit,
  onAnalytics,
  onDelete,
  onToggle,
  onCopy,
  pending,
}: {
  links: Link[];
  total: number;
  page: number;
  pageSize: number;
  loading: boolean;
  search: string;
  status: LinkStatus;
  onPage: (page: number) => void;
  onCreate: () => void;
  onEdit: (link: Link) => void;
  onAnalytics: (link: Link) => void;
  onDelete: (link: Link) => void;
  onToggle: (link: Link) => void;
  onCopy: (url: string) => void;
  pending: string | null;
}) {
  if (loading && !links.length)
    return (
      <div className="loading-block">
        <Spinner /> Loading your links…
      </div>
    );
  if (!links.length)
    return (
      <div className="empty-state">
        <div className="empty-icon">
          <Icon
            name={search || status !== "all" ? "search" : "link"}
            size={28}
          />
        </div>
        <h3>
          {search || status !== "all"
            ? "No links match this view"
            : "Your next good link starts here"}
        </h3>
        <p>
          {search || status !== "all"
            ? "Try a different search or choose another status."
            : "Shorten a portfolio, an article, a product page — anything you want to share."}
        </p>
        {!search && status === "all" && (
          <button className="button primary" onClick={onCreate}>
            <Icon name="plus" size={17} /> Create your first link
          </button>
        )}
      </div>
    );
  return (
    <>
      <div className={`table-wrap ${loading ? "is-refreshing" : ""}`}>
        <table className="links-table">
          <thead>
            <tr>
              <th scope="col">Link & destination</th>
              <th scope="col">Status</th>
              <th scope="col" className="clicks-heading">
                Clicks
              </th>
              <th scope="col" className="created-column">
                Created
              </th>
              <th scope="col">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {links.map((link) => (
              <tr key={link.id}>
                <td>
                  <div className="link-cell">
                    <div className="destination-icon">
                      <Icon name="globe" size={20} />
                    </div>
                    <div className="link-cell-content">
                      <button
                        className="link-title"
                        onClick={() => onAnalytics(link)}
                      >
                        {link.title || hostname(link.original_url)}
                      </button>
                      <div className="short-url-line">
                        <a
                          href={link.short_url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {displayUrl(link.short_url)}
                        </a>
                        <button
                          className="icon-button copy-inline"
                          aria-label={`Copy ${link.title || link.short_code}`}
                          title="Copy short link"
                          onClick={() => onCopy(link.short_url)}
                        >
                          <Icon name="copy" size={13} />
                        </button>
                      </div>
                      <p className="destination-url" title={link.original_url}>
                        {displayUrl(link.original_url)}
                      </p>
                    </div>
                  </div>
                </td>
                <td>
                  <StatusBadge link={link} />
                </td>
                <td className="click-count">
                  <button
                    onClick={() => onAnalytics(link)}
                    title="View click analytics"
                  >
                    {count(link.click_count)}
                    <Icon name="chart" size={14} />
                  </button>
                </td>
                <td className="created-column">
                  <span
                    className="created-date"
                    title={fullDate(link.created_at)}
                  >
                    {shortDate(link.created_at)}
                  </span>
                </td>
                <td>
                  <div className="row-actions">
                    <button
                      className="icon-button"
                      aria-label={`Analytics for ${link.title || link.short_code}`}
                      title="View analytics"
                      onClick={() => onAnalytics(link)}
                    >
                      <Icon name="chart" size={17} />
                    </button>
                    <button
                      className="icon-button"
                      aria-label={`Edit ${link.title || link.short_code}`}
                      title="Edit link"
                      onClick={() => onEdit(link)}
                    >
                      <Icon name="edit" size={16} />
                    </button>
                    <button
                      className="icon-button"
                      aria-label={`${link.is_active ? "Pause" : "Resume"} ${link.title || link.short_code}`}
                      title={link.is_active ? "Pause link" : "Resume link"}
                      disabled={
                        pending === link.id || linkStatus(link) === "expired"
                      }
                      onClick={() => onToggle(link)}
                    >
                      {pending === link.id ? (
                        <Spinner />
                      ) : (
                        <Icon
                          name={link.is_active ? "pause" : "play"}
                          size={16}
                        />
                      )}
                    </button>
                    <button
                      className="icon-button delete-action"
                      aria-label={`Delete ${link.title || link.short_code}`}
                      title="Delete link"
                      onClick={() => onDelete(link)}
                    >
                      <Icon name="trash" size={16} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <footer className="table-footer">
        <span>
          Showing{" "}
          <strong>
            {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)}
          </strong>{" "}
          of <strong>{count(total)}</strong> links
        </span>
        <div className="pagination">
          <button
            className="icon-button"
            aria-label="Previous page"
            disabled={page <= 1 || loading}
            onClick={() => onPage(page - 1)}
          >
            <Icon name="left" size={17} />
          </button>
          <span>
            Page {page} of {Math.max(1, Math.ceil(total / pageSize))}
          </span>
          <button
            className="icon-button"
            aria-label="Next page"
            disabled={page * pageSize >= total || loading}
            onClick={() => onPage(page + 1)}
          >
            <Icon name="right" size={17} />
          </button>
        </div>
      </footer>
    </>
  );
}

function Workspace({
  session,
  onLogout,
}: {
  session: Session;
  onLogout: () => void;
}) {
  const [view, setView] = useState<"overview" | "links">("overview");
  const [mobileNav, setMobileNav] = useState(false);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [dashboardError, setDashboardError] = useState("");
  const [days, setDays] = useState(30);
  const [list, setList] = useState<LinkList>({
    items: [],
    total: 0,
    page: 1,
    page_size: 8,
  });
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<LinkStatus>("all");
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [editing, setEditing] = useState<Link | null | undefined>(undefined);
  const [analytics, setAnalytics] = useState<Link | null>(null);
  const [deleting, setDeleting] = useState<Link | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [toast, setToast] = useState<{
    message: string;
    error?: boolean;
  } | null>(null);
  const token = session.access_token;
  const pageSize = 8;
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 4500);
      return () => clearTimeout(timer);
    }
  }, [toast]);
  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(search);
      setPage(1);
    }, 280);
    return () => clearTimeout(timer);
  }, [search]);
  useEffect(() => {
    const controller = new AbortController();
    request<Dashboard>(`/dashboard?days=${days}`, token, {
      signal: controller.signal,
    })
      .then((result) => {
        setDashboard(result);
        setDashboardError("");
      })
      .catch((err) => {
        if (!controller.signal.aborted) setDashboardError(humanError(err));
      });
    return () => controller.abort();
  }, [token, days, revision]);
  useEffect(() => {
    const controller = new AbortController();
    setListLoading(true);
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
      search: query,
      status,
    });
    request<LinkList>(`/urls?${params}`, token, { signal: controller.signal })
      .then((result) => {
        setList(result);
        setListError("");
        if (result.total && !result.items.length && page > 1)
          setPage(Math.max(1, Math.ceil(result.total / pageSize)));
      })
      .catch((err) => {
        if (!controller.signal.aborted) setListError(humanError(err));
      })
      .finally(() => {
        if (!controller.signal.aborted) setListLoading(false);
      });
    return () => controller.abort();
  }, [token, page, query, status, revision]);
  useEffect(() => {
    const interval = setInterval(() => {
      if (!document.hidden) refresh();
    }, 15_000);
    return () => clearInterval(interval);
  }, [refresh]);
  async function toggle(link: Link) {
    setPending(link.id);
    try {
      await request<Link>(`/urls/${link.id}`, token, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !link.is_active }),
      });
      refresh();
      setToast({
        message: link.is_active
          ? "Link paused. You can resume it any time."
          : "Link is active again.",
      });
    } catch (err) {
      setToast({ message: humanError(err), error: true });
    } finally {
      setPending(null);
    }
  }
  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      setToast({ message: "Short link copied. Ready to share." });
    } catch {
      setToast({
        message:
          "Clipboard access is unavailable. Select and copy the short URL instead.",
        error: true,
      });
    }
  }
  function navigate(next: "overview" | "links") {
    setView(next);
    setMobileNav(false);
  }
  const firstName = session.user.name.split(" ")[0] || "there";
  return (
    <div className="app-shell">
      {mobileNav && (
        <div className="nav-scrim" onClick={() => setMobileNav(false)} />
      )}
      <aside className={`sidebar ${mobileNav ? "is-open" : ""}`}>
        <Brand />
        <div className="workspace-label">
          <span className="workspace-avatar">
            {session.user.name.slice(0, 1).toUpperCase()}
          </span>
          <div>
            <strong>Personal workspace</strong>
            <span>Your links, in one place</span>
          </div>
        </div>
        <span className="nav-caption">WORKSPACE</span>
        <nav aria-label="Main navigation">
          <button
            className={view === "overview" ? "nav-item active" : "nav-item"}
            onClick={() => navigate("overview")}
          >
            <Icon name="overview" size={19} />
            Overview
          </button>
          <button
            className={view === "links" ? "nav-item active" : "nav-item"}
            onClick={() => navigate("links")}
          >
            <Icon name="link" size={19} />
            Your links
            {dashboard && (
              <span className="nav-count">{count(dashboard.total_links)}</span>
            )}
          </button>
          <a className="nav-item" href="/docs" target="_blank" rel="noreferrer">
            <Icon name="code" size={19} />
            API documentation
            <Icon name="external" size={13} />
          </a>
        </nav>
        <div className="sidebar-tip">
          <div className="tip-icon">
            <Icon name="link" size={21} />
          </div>
          <h3>Make it memorable.</h3>
          <p>
            A custom short code helps your next link feel a little more like
            you.
          </p>
          <button
            onClick={() => {
              setEditing(null);
              setMobileNav(false);
            }}
          >
            Create a custom link <Icon name="arrow" size={16} />
          </button>
        </div>
        <div className="sidebar-account">
          <span className="account-avatar">
            {session.user.name.slice(0, 2).toUpperCase()}
          </span>
          <div>
            <strong>{session.user.name}</strong>
            <span title={session.user.email}>{session.user.email}</span>
          </div>
          <button
            className="icon-button"
            onClick={onLogout}
            aria-label="Sign out"
            title="Sign out"
          >
            <Icon name="logout" size={18} />
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMobileNav(true)}
            >
              <Icon name="menu" />
            </button>
            <span>Workspace</span>
            <Icon name="right" size={14} />
            <strong>{view === "overview" ? "Overview" : "Your links"}</strong>
          </div>
          <div className="topbar-right">
            <span className="topbar-status">
              <span className="tiny-dot" /> Personal workspace
            </span>
            <span className="topbar-avatar">
              {session.user.name.slice(0, 1).toUpperCase()}
            </span>
          </div>
        </header>
        <main className="main-content" id="main-content">
          <section className="page-heading">
            <div>
              <span className="section-kicker">
                {view === "overview"
                  ? `HELLO, ${firstName.toUpperCase()}`
                  : "LESS LENGTH. MORE POSSIBILITY."}
              </span>
              <h1>
                {view === "overview"
                  ? "Make every link count."
                  : "All your links. One place."}
              </h1>
              <p>
                {view === "overview"
                  ? "A little clarity on everything you share."
                  : "Create, organize, and fine-tune the links you share."}
              </p>
            </div>
            <button className="button primary" onClick={() => setEditing(null)}>
              <Icon name="plus" size={19} /> Create link
            </button>
          </section>
          {dashboardError && (
            <ErrorBanner onRetry={refresh}>{dashboardError}</ErrorBanner>
          )}
          <section className="stats-grid" aria-label="Workspace statistics">
            <StatCard
              label="Total links"
              value={dashboard?.total_links}
              detail="Everything you’ve created"
              icon="link"
            />
            <StatCard
              label="All-time clicks"
              value={dashboard?.total_clicks}
              detail="Visits across your links"
              icon="cursor"
            />
            <StatCard
              label={`Clicks · last ${days} days`}
              value={dashboard?.period_clicks}
              detail="A snapshot of recent activity"
              icon="chart"
              tone="stat-highlight"
            />
            <StatCard
              label="Active links"
              value={dashboard?.active_links}
              detail="Ready for their next click"
              icon="check"
            />
          </section>
          {view === "overview" && (
            <section className="insights-grid">
              <div className="panel activity-panel">
                <div className="panel-heading">
                  <div>
                    <h2>Click activity</h2>
                    <p>See when your links get noticed.</p>
                  </div>
                  <label className="period-select">
                    <span className="sr-only">Activity period</span>
                    <select
                      value={days}
                      onChange={(e) => setDays(Number(e.target.value))}
                    >
                      {[7, 30, 90].map((value) => (
                        <option key={value} value={value}>
                          Last {value} days
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <div className="activity-total">
                  <strong>
                    {dashboard ? count(dashboard.period_clicks) : "—"}
                  </strong>
                  <span>clicks in this period</span>
                  <span className="chart-legend">
                    <span /> Clicks
                  </span>
                </div>
                {dashboard ? (
                  <ActivityChart data={dashboard.clicks_by_day} />
                ) : (
                  <div className="loading-block chart-loading">
                    <Spinner /> Loading activity…
                  </div>
                )}
              </div>
              <div className="panel top-links-panel">
                <div className="panel-heading">
                  <div>
                    <h2>In the spotlight</h2>
                    <p>Your most-clicked destinations.</p>
                  </div>
                  <Icon name="chart" size={19} />
                </div>
                {dashboard?.top_links.length ? (
                  <div className="top-links-list">
                    {dashboard.top_links.slice(0, 4).map((link, index) => (
                      <button
                        key={link.id}
                        className="top-link"
                        onClick={() => setAnalytics(link)}
                      >
                        <span className="rank">0{index + 1}</span>
                        <div>
                          <strong>
                            {link.title || hostname(link.original_url)}
                          </strong>
                          <span>{link.short_code}</span>
                        </div>
                        <span className="top-link-count">
                          {count(link.click_count)}
                          <Icon name="arrow" size={14} />
                        </span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="spotlight-empty">
                    <span className="spotlight-art">
                      <Icon name="cursor" size={28} />
                    </span>
                    <h3>Your next standout link?</h3>
                    <p>
                      Once your links get clicks, your top performers will
                      appear here.
                    </p>
                  </div>
                )}
                <div className="insight-footer">
                  <Icon name="clock" size={14} />
                  <span>Analytics can take a few seconds to catch up.</span>
                </div>
              </div>
            </section>
          )}
          <section className="panel links-panel">
            <div className="links-section-heading">
              <div>
                <h2>
                  {view === "overview" ? "Your links" : "Link collection"}
                  <span className="count-badge">{count(list.total)}</span>
                </h2>
                <p>A shortcut to every destination.</p>
              </div>
              <button
                className="text-button refresh-button"
                onClick={refresh}
                title="Refresh links and analytics"
              >
                <Icon name="refresh" size={15} /> Refresh
              </button>
            </div>
            <div className="table-toolbar">
              <label className="search-field">
                <Icon name="search" size={18} />
                <span className="sr-only">Search links</span>
                <input
                  type="search"
                  placeholder="Search title, destination, or short code…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </label>
              <label className="status-filter">
                <span className="sr-only">Filter links by status</span>
                <select
                  value={status}
                  onChange={(e) => {
                    setStatus(e.target.value as LinkStatus);
                    setPage(1);
                  }}
                >
                  <option value="all">All statuses</option>
                  <option value="active">Active</option>
                  <option value="inactive">Paused</option>
                  <option value="expired">Expired</option>
                </select>
              </label>
            </div>
            {listError && (
              <div className="table-error">
                <ErrorBanner onRetry={refresh}>{listError}</ErrorBanner>
              </div>
            )}
            <LinkTable
              links={list.items}
              total={list.total}
              page={page}
              pageSize={pageSize}
              loading={listLoading}
              search={query}
              status={status}
              onPage={setPage}
              onCreate={() => setEditing(null)}
              onEdit={setEditing}
              onAnalytics={setAnalytics}
              onDelete={setDeleting}
              onToggle={toggle}
              onCopy={copy}
              pending={pending}
            />
          </section>
          <footer className="workspace-footer">
            <span>Made for good connections.</span>
            <span>
              Linkforge <span className="footer-dot">·</span> Counts reflect
              recorded visits, including repeat clicks.
            </span>
          </footer>
        </main>
      </div>
      {editing !== undefined && (
        <LinkModal
          link={editing}
          token={token}
          onClose={() => setEditing(undefined)}
          onSaved={() => {
            const wasNew = editing === null;
            setEditing(undefined);
            setPage(1);
            refresh();
            setToast({
              message: wasNew
                ? "Your short link is ready to share."
                : "Link updated successfully.",
            });
          }}
        />
      )}
      {analytics && (
        <AnalyticsModal
          link={analytics}
          token={token}
          onClose={() => setAnalytics(null)}
        />
      )}
      {deleting && (
        <DeleteModal
          link={deleting}
          token={token}
          onClose={() => setDeleting(null)}
          onDeleted={() => {
            setDeleting(null);
            refresh();
            setToast({ message: "Link deleted from your workspace." });
          }}
        />
      )}
      {toast && (
        <div
          className={`toast ${toast.error ? "toast-error" : ""}`}
          role={toast.error ? "alert" : "status"}
        >
          <Icon name={toast.error ? "warning" : "check"} size={19} />
          <span>{toast.message}</span>
          <button
            aria-label="Dismiss notification"
            onClick={() => setToast(null)}
          >
            <Icon name="close" size={16} />
          </button>
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [session, setSession] = useState<Session | null>(loadSession);
  const [notice, setNotice] = useState("");
  const login = useCallback((next: Session) => {
    saveSession(next);
    setSession(next);
    setNotice("");
  }, []);
  const logout = useCallback((message = "") => {
    saveSession(null);
    setSession(null);
    setNotice(message);
  }, []);
  useEffect(() => {
    const expired = () =>
      logout("Your session has expired. Sign in to continue.");
    window.addEventListener("linkforge:unauthorized", expired);
    return () => window.removeEventListener("linkforge:unauthorized", expired);
  }, [logout]);
  useEffect(() => {
    if (!session) return;
    const timer = setTimeout(
      () => logout("Your session has expired. Sign in to continue."),
      Math.max(0, session.expires_at - Date.now()),
    );
    return () => clearTimeout(timer);
  }, [session, logout]);
  useEffect(() => {
    if (!session) return;
    const controller = new AbortController();
    request<User>("/auth/me", session.access_token, {
      signal: controller.signal,
    }).catch((err) => {
      if (err instanceof ApiError && err.status === 401)
        logout("Please sign in again to continue.");
    });
    return () => controller.abort();
  }, [session, logout]);
  return session ? (
    <Workspace
      session={session}
      onLogout={() => logout("You’ve been signed out.")}
    />
  ) : (
    <AuthScreen onLogin={login} notice={notice} />
  );
}
