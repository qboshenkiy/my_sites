package net.sbena.updates;
import org.junit.Test;
import static org.junit.Assert.*;
public class AppUpdatesTest {
    @Test public void firstLaunchAndManualChecksBypassResumeThrottle() {
        long now=1000000L;
        assertTrue(AppUpdates.shouldCheck(false,false,now,now-1000));
        assertTrue(AppUpdates.shouldCheck(true,true,now,now-1000));
        assertFalse(AppUpdates.shouldCheck(true,false,now,now-1000));
        assertTrue(AppUpdates.shouldCheck(true,false,now,now-900000));
        assertTrue(AppUpdates.shouldCheck(true,false,now,now+1000));
    }
    @Test public void onlyOfficialReleaseApksAreAccepted() {
        assertTrue(AppUpdates.validAsset("https://github.com/qboshenkiy/my_sites/releases/download/android-101/marathon.apk"));
        for(String url:new String[]{"http://github.com/qboshenkiy/my_sites/releases/download/android-1/a.apk","https://evil.test/a.apk","https://github.com/other/repo/releases/download/android-1/a.apk","https://github.com/qboshenkiy/my_sites/releases/download/android-1/a.apk?redirect=evil","https://user@github.com/qboshenkiy/my_sites/releases/download/android-1/a.apk","https://github.com/qboshenkiy/my_sites/releases/download/android-1/../a.apk"}) assertFalse(url,AppUpdates.validAsset(url));
    }
}
