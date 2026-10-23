using System;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;
using UnityTranslator.KryptaFM;

public static class PluginTests {
    private static int checks;
    private static void Require(bool condition) { if(!condition) throw new Exception("Synthetic plugin check failed: "+checks); checks++; }
    private static void Call(Plugin plugin,string method,object argument) {
        typeof(Plugin).GetMethod(method,BindingFlags.NonPublic|BindingFlags.Instance).Invoke(plugin,new object[]{argument});
    }
    private static Plugin Create() {
        string journal="Objective"+new string('\n',11), journalTarget="Görev"+new string('\n',11);
        Payload payload=new Payload {format_version=1,profile_id="krypta-fm-textassets",unity_version="synthetic",
            assembly_sha256=new string('a',64),source_language="en",target_language="tr",entries=new Entry[]{
                new Entry {source_id="s",asset_name="Synthetic",schema="subtitle-lines-v1",
                    source_sha256=TranslationCore.Digest("Original\n"),target_sha256=TranslationCore.Digest("Translated\n"),text="Translated\n"},
                new Entry {source_id="journal",asset_name="Journal.objectivesDescriptionsENG",schema="journal-lines-v1",
                    source_sha256=TranslationCore.Digest(journal),target_sha256=TranslationCore.Digest(journalTarget),text=journalTarget}
            }};
        Plugin plugin=new Plugin();
        typeof(Plugin).GetField("core",BindingFlags.NonPublic|BindingFlags.Instance).SetValue(plugin,new TranslationCore(payload,"synthetic",new string('a',64)));
        return plugin;
    }
    private static TextAsset Source() { return new TextAsset("Original\n"){name="Synthetic"}; }
    public static void Main() {
        TranslateManager.instance=new TranslateManager();
        Plugin plugin=Create(); TextAsset original=Source();
        TranslateManager menu=new TranslateManager {textAssetEng=original};
        Call(plugin,"Menu",menu); Require(menu.textAssetEng!=original); Require(menu.textAssetEng.text=="Translated\n");
        TextAsset clone=menu.textAssetEng; Call(plugin,"Menu",menu); Require(menu.textAssetEng==clone);
        menu.currentTranslation=clone.text.Split('\n'); Call(plugin,"Stop",99);
        Require(menu.textAssetEng==original); Require(menu.currentTranslation[0]=="Original");
        Call(plugin,"Menu",menu); Require(menu.textAssetEng==original);
        plugin=Create(); menu=new TranslateManager {isPolish=true,textAssetEng=original};
        Call(plugin,"Menu",menu); Require(menu.textAssetEng==original);
        menu.isPolish=false; Call(plugin,"Menu",menu); menu.isPolish=true; menu.currentTranslation=new string[]{"Polish"};
        Call(plugin,"Stop",99); Require(menu.currentTranslation[0]=="Polish");
        plugin=Create();
        SubtitlesManager subs=new SubtitlesManager {subtitlesListENG=new List<TextAsset>{original}};
        Call(plugin,"Subtitles",subs); subs.currentSubtitlesList=new List<TextAsset>(subs.subtitlesListENG);
        Call(plugin,"SelectedSubtitles",subs); subs.currentSubtitlesString=subs.currentSubtitlesList[0].text.Split('\n');
        Require(subs.currentSubtitlesString[0]=="Translated"); Call(plugin,"Stop",99);
        Require(subs.subtitlesListENG[0]==original); Require(subs.currentSubtitlesList[0]==original);
        Require(subs.currentSubtitlesString[0]=="Original");
        plugin=Create(); subs=new SubtitlesManager {currentSubtitlesList=new List<TextAsset>{original}};
        Call(plugin,"SelectedSubtitles",subs); subs.currentSubtitlesString=subs.currentSubtitlesList[0].text.Split('\n');
        Call(plugin,"Stop",99); Require(subs.currentSubtitlesList[0]==original); Require(subs.currentSubtitlesString[0]=="Original");
        plugin=Create();
        List<TextAsset> posts=new List<TextAsset>{original};
        PostInfoManager post=new PostInfoManager {postScriptsListENG=posts,keyPostScriptsListENG=new List<TextAsset>(),
            messagesListENG=new List<TextAsset>{new TextAsset("Wrong"){name="Synthetic"}}};
        Call(plugin,"Posts",post); Require(post.postScriptsListENG==posts); Require(posts[0]==original);
        plugin=Create(); post.messagesListENG=new List<TextAsset>(); Call(plugin,"Posts",post);
        post.currentPostScriptsList=new List<TextAsset>(post.postScriptsListENG);
        Require(post.currentPostScriptsList[0].text=="Translated\n"); Call(plugin,"Stop",99);
        Require(post.postScriptsListENG==posts); Require(post.currentPostScriptsList[0]==original);
        plugin=Create();
        string[,] grid=new string[4,3];
        for(int row=0;row<4;row++) for(int column=0;column<3;column++) grid[row,column]="";
        grid[0,0]="Objective";
        Journal journalManager=new Journal(grid);
        object[] invocation=new object[]{journalManager,grid};
        MethodInfo hook=typeof(Plugin).GetMethod("JournalText",BindingFlags.NonPublic|BindingFlags.Instance);
        hook.Invoke(plugin,invocation);
        string[,] translated=(string[,])invocation[1];
        typeof(Journal).GetField("objectivesDescriptionsENG",BindingFlags.NonPublic|BindingFlags.Instance).SetValue(journalManager,translated);
        Require(translated!=grid); Require(translated[0,0]=="Görev"); Require(grid[0,0]=="Objective");
        Require(translated[3,2]=="");
        invocation=new object[]{journalManager,translated}; hook.Invoke(plugin,invocation); Require(invocation[1]==translated);
        Call(plugin,"Stop",99); Require(journalManager.Read()==grid);
        plugin=Create();
        string[,] malformed=new string[1,1]{{"Objective"}};
        journalManager=new Journal(malformed); invocation=new object[]{journalManager,malformed}; hook.Invoke(plugin,invocation);
        Require(journalManager.Read()==malformed); Require(invocation[1]==malformed);
        Console.WriteLine(checks+" synthetic plugin lifecycle checks passed; no game assembly executed.");
    }
}
