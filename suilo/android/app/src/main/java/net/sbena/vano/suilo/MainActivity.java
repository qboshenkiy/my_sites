package net.sbena.vano.suilo;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(StudyBackupPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
