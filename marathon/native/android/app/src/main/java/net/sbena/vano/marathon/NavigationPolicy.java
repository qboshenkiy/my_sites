package net.sbena.vano.marathon;

import java.net.URI;
import java.util.Locale;

/** Keep session-bearing navigation inside the configured website. No JS/native bridge. */
public final class NavigationPolicy {
    private final URI base;
    private final String prefix;
    public NavigationPolicy(String url) { this(url, false); }
    public NavigationPolicy(String url, boolean allowHttpDebug) {
        base = URI.create(url).normalize();
        boolean temporaryHttp = allowHttpDebug && "http".equals(base.getScheme())
                && "vano.sbena.net".equals(base.getHost()) && base.getPort() == 8081;
        if ((!"https".equals(base.getScheme()) && !temporaryHttp) || base.getHost() == null || base.getUserInfo() != null
                || base.getQuery() != null || base.getFragment() != null) throw new IllegalArgumentException("HTTPS required");
        String path = base.getPath();
        prefix = path == null || path.isEmpty() ? "/" : (path.endsWith("/") ? path : path + "/");
    }
    private static int port(URI url) { return url.getPort() == -1 ? ("http".equals(url.getScheme()) ? 80 : 443) : url.getPort(); }
    public boolean internal(String value) {
        try {
            URI url = URI.create(value).normalize();
            if (!base.getScheme().equals(url.getScheme()) || url.getHost() == null || url.getUserInfo() != null
                    || !base.getHost().equalsIgnoreCase(url.getHost()) || port(base) != port(url)) return false;
            String path = url.getPath();
            if (path == null || path.isEmpty()) path = "/";
            for (String part : path.split("/")) if (part.equals("..") || part.equals(".")) return false;
            return path.startsWith(prefix);
        } catch (IllegalArgumentException error) { return false; }
    }
    public boolean external(String value) {
        try {
            URI url = URI.create(value);
            String scheme = url.getScheme() == null ? "" : url.getScheme().toLowerCase(Locale.ROOT);
            return ((scheme.equals("https") || scheme.equals("http")) && url.getHost() != null && url.getUserInfo() == null)
                    || (scheme.equals("tg") && "resolve".equals(url.getHost()));
        } catch (IllegalArgumentException error) { return false; }
    }
}
