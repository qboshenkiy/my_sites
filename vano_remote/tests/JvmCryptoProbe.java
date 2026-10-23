package net.sbena.vano.remote;

import java.util.Base64;
import org.json.JSONObject;

/** Executes the actual Android client's static crypto code on the JVM. */
public class JvmCryptoProbe {
    public static void main(String[] args) throws Exception {
        byte[] key=Link.unhex(args[0]);
        System.out.println(Link.open(key,Base64.getDecoder().decode(args[1])).toString());
        System.out.println(Base64.getEncoder().encodeToString(Link.seal(key,new JSONObject().put("type","probe").put("value","Привет"))));
        System.out.println(Link.hex(Link.hash(Link.utf("e2e:"+args[2]))));
    }
}
