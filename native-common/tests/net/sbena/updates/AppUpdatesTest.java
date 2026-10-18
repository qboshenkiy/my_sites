package net.sbena.updates;
import org.junit.Test;
import static org.junit.Assert.*;
public class AppUpdatesTest {
    @Test public void onlyOfficialReleaseApksAreAccepted() {
        assertTrue(AppUpdates.validAsset("https://github.com/qboshenkiy/my_sites/releases/download/android-101/marathon.apk"));
        for(String url:new String[]{"http://github.com/qboshenkiy/my_sites/releases/download/android-1/a.apk","https://evil.test/a.apk","https://github.com/other/repo/releases/download/android-1/a.apk","https://github.com/qboshenkiy/my_sites/releases/download/android-1/a.apk?redirect=evil","https://user@github.com/qboshenkiy/my_sites/releases/download/android-1/a.apk","https://github.com/qboshenkiy/my_sites/releases/download/android-1/../a.apk"}) assertFalse(url,AppUpdates.validAsset(url));
    }
}
