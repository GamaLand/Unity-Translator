using System;
using UnityTranslator.KryptaFM;

public static class CoreTests
{
    private static int checks;
    private static void Require(bool value) { if(!value) throw new Exception("Synthetic runtime check failed."); checks++; }
    private static void Reject(Action action)
    { bool failed=false; try { action(); } catch(FormatException) { failed=true; } Require(failed); }
    public static void Main()
    {
        string original="01\r\n123\r\n01.02.2006 9:12\r\nTitle\r\nBody\r\np00\r\n02\r\nReply\r\np01";
        string translated=original.Replace("Title","Başlık").Replace("Body","İçerik").Replace("Reply","Yanıt");
        Entry entry=new Entry {source_id="synthetic",asset_name="Synthetic",schema="forum-lines-v1",
            source_sha256=TranslationCore.Digest(original),target_sha256=TranslationCore.Digest(translated),text=translated};
        Payload payload=new Payload {format_version=1,profile_id="krypta-fm-textassets",unity_version="synthetic",
            assembly_sha256=new string('a',64),source_language="en",target_language="tr",entries=new Entry[]{entry}};
        TranslationCore core=new TranslationCore(payload,"synthetic",new string('a',64));
        Require(core.Translate("Synthetic",original)==translated);
        Require(core.Translate("Unrelated",original)==original);
        Reject(()=>core.Translate("Synthetic",original+"changed"));
        Reject(()=>TranslationCore.VerifyLayout(original,translated.Replace("123","999"),"forum-lines-v1"));
        Reject(()=>TranslationCore.VerifyLayout(original,translated.Replace("p01","p02"),"forum-lines-v1"));
        Reject(()=>TranslationCore.VerifyLayout(original,translated+"\nInjected","forum-lines-v1"));
        Reject(()=>TranslationCore.VerifyLayout(original,translated.Replace("\r\n","\n"),"forum-lines-v1"));
        TranslationCore.VerifyLayout("< back\n\nNext\n","< geri\n\nSonraki\n","subtitle-lines-v1"); checks++;
        TranslationCore.VerifyLayout("01\n2\n01.02.2006 9:12\nTitle\nBody\n02\nReply\np00",
            "01\n2\n01.02.2006 9:12\nBaşlık\nİçerik\n02\nYanıt\np00","keypost-lines-v1"); checks++;
        entry.text="caller mutation"; Require(core.Translate("Synthetic",original)==translated);
        payload.entries=new Entry[]{entry,entry}; Reject(()=>new TranslationCore(payload,"synthetic",new string('a',64)));
        string json="{\"format_version\":1,\"profile_id\":\"krypta-fm-textassets\",\"unity_version\":\"synthetic\",\"assembly_sha256\":\""+new string('a',64)+"\",\"source_language\":\"en\",\"target_language\":\"tr\",\"entries\":[{\"source_id\":\"one\",\"asset_name\":\"Synthetic\",\"schema\":\"subtitle-lines-v1\",\"source_sha256\":\""+TranslationCore.Digest("Source")+"\",\"target_sha256\":\""+TranslationCore.Digest("Çeviri")+"\",\"text\":\"Çeviri\"}]}";
        Require(new TranslationCore(PayloadJson.Parse(json),"synthetic",new string('a',64)).Translate("Synthetic","Source")=="Çeviri");
        Reject(()=>PayloadJson.Parse(json.Replace("\"format_version\":1","\"format_version\":1,\"format_version\":1")));
        Reject(()=>PayloadJson.Parse(json.Replace("\"asset_name\"","\"command\"")));
        Reject(()=>PayloadJson.Parse(json+" trailing"));
        string journal="Objective\n\n\n\n\n\n\n\n\n\n\n";
        TranslationCore.VerifyLayout(journal,journal.Replace("Objective","Hedef"),"journal-lines-v1"); checks++;
        Reject(()=>TranslationCore.VerifyLayout(journal,journal+"\n","journal-lines-v1"));
        Reject(()=>TranslationCore.VerifyLayout(journal,journal.Replace("\n\n","\nInjected\n"),"journal-lines-v1"));
        Console.WriteLine(checks+" synthetic Krypta FM runtime data checks passed; no game assembly executed.");
    }
}
