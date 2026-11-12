package net.sbena.vano.suilo;

import android.app.Activity;
import android.content.Intent;
import androidx.activity.result.ActivityResult;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.ActivityCallback;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

/** Export only to a document explicitly chosen through Android's system picker. */
@CapacitorPlugin(name = "StudyBackup")
public class StudyBackupPlugin extends Plugin {
    @PluginMethod
    public void save(PluginCall call) {
        String text = call.getString("text");
        String filename = call.getString("filename", "suilo-words.json");
        if (text == null || text.length() > 2_000_000 || !filename.matches("suilo-words-[0-9-]+\\.json")) {
            call.reject("Некорректная резервная копия.");
            return;
        }
        Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("application/json");
        intent.putExtra(Intent.EXTRA_TITLE, filename);
        try {
            startActivityForResult(call, intent, "documentChosen");
        } catch (Exception error) {
            call.reject("Не удалось открыть выбор файла.");
        }
    }

    @ActivityCallback
    private void documentChosen(PluginCall call, ActivityResult result) {
        if (call == null) return;
        JSObject response = new JSObject();
        if (result.getResultCode() != Activity.RESULT_OK || result.getData() == null || result.getData().getData() == null) {
            response.put("cancelled", true);
            call.resolve(response);
            return;
        }
        try (OutputStream stream = getContext().getContentResolver().openOutputStream(result.getData().getData(), "w")) {
            if (stream == null) throw new java.io.IOException("No output stream");
            String text = call.getString("text");
            if (text == null) throw new java.io.IOException("No backup data");
            stream.write(text.getBytes(StandardCharsets.UTF_8));
            response.put("cancelled", false);
            call.resolve(response);
        } catch (Exception error) {
            call.reject("Не удалось сохранить резервную копию.");
        }
    }
}
