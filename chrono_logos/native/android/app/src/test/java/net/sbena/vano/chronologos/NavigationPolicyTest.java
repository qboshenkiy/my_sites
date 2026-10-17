package net.sbena.vano.chronologos;

import org.junit.Test;
import static org.junit.Assert.*;

public class NavigationPolicyTest {
    private final NavigationPolicy policy = new NavigationPolicy("https://vano.sbena.net/reading/");
    @Test public void preservesOnlyTrustedOriginAndFolder() {
        assertTrue(policy.internal("https://vano.sbena.net/reading/api.php?action=profile"));
        assertTrue(policy.internal("https://vano.sbena.net:443/reading/"));
        assertFalse(policy.internal("https://vano.sbena.net.evil.test/reading/"));
        assertFalse(policy.internal("https://vano.sbena.net:8081/reading/"));
        assertFalse(policy.internal("http://vano.sbena.net/reading/"));
        assertFalse(policy.internal("https://user@vano.sbena.net/reading/"));
        assertFalse(policy.internal("https://vano.sbena.net/reading/../admin/"));
        assertFalse(policy.internal("https://vano.sbena.net/reading/%2e%2e/admin/"));
        assertFalse(policy.internal("https://vano.sbena.net/reading-other/"));
        assertFalse(policy.internal("file:///data/data/private"));
    }
    @Test public void externalLinksDoNotGrantNativeCodeAccess() {
        assertTrue(policy.external("https://t.me/example_bot?start=login"));
        assertTrue(policy.external("tg://resolve?domain=example_bot"));
        assertFalse(policy.external("javascript:alert(1)"));
        assertFalse(policy.external("intent://private#Intent;end"));
        assertFalse(policy.external("file:///data/data/private"));
        assertFalse(policy.external("tg://unsafe-command"));
    }
    @Test public void gamePortIsPartOfTrustedOrigin() {
        NavigationPolicy game = new NavigationPolicy("https://vano.sbena.net:8083/");
        assertTrue(game.internal("https://vano.sbena.net:8083/rooms"));
        assertFalse(game.internal("https://vano.sbena.net/rooms"));
        assertFalse(game.internal("http://vano.sbena.net:8083/rooms"));
        assertFalse(game.internal("https://vano.sbena.net:8081/rooms"));
        assertThrows(IllegalArgumentException.class, () -> new NavigationPolicy("http://vano.sbena.net:8083/"));
    }
}
