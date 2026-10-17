package net.sbena.vano.marathon;

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
    @Test public void temporaryHttpIsExplicitAndRestrictedToCurrentServer() {
        NavigationPolicy temporary = new NavigationPolicy("http://vano.sbena.net:8081/", true);
        assertTrue(temporary.internal("http://vano.sbena.net:8081/api.php?action=profile"));
        assertFalse(temporary.internal("http://vano.sbena.net/"));
        assertFalse(temporary.internal("http://vano.sbena.net:8083/"));
        assertFalse(temporary.internal("http://sub.vano.sbena.net:8081/"));
        assertFalse(temporary.internal("https://vano.sbena.net:8081/"));
        assertFalse(temporary.internal("http://user@vano.sbena.net:8081/"));
        assertFalse(new NavigationPolicy("https://vano.sbena.net/", true).internal("http://vano.sbena.net:8081/"));
        for (String address : new String[]{"http://vano.sbena.net:8083/", "http://other.test:8081/", "http://vano.sbena.net:8081/?token=secret"}) {
            assertThrows(IllegalArgumentException.class, () -> new NavigationPolicy(address, true));
        }
        assertThrows(IllegalArgumentException.class, () -> new NavigationPolicy("http://vano.sbena.net:8081/"));
    }
}
