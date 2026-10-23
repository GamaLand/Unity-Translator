using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using BepInEx;
using HarmonyLib;
using UnityEngine;

namespace UnityTranslator.KryptaFM
{
    [BepInPlugin("org.unitytranslator.kryptafm", "UnityTranslator Krypta FM (experimental)", "0.1.0")]
    public sealed class Plugin : BaseUnityPlugin
    {
        private static Plugin active;
        private TranslationCore core;
        private Harmony harmony;
        private bool stopped;
        private readonly Dictionary<TextAsset,TextAsset> replacements=new Dictionary<TextAsset,TextAsset>();
        private readonly Dictionary<TextAsset,TextAsset> originals=new Dictionary<TextAsset,TextAsset>();
        private readonly List<Action> undo=new List<Action>();
        private readonly HashSet<Journal> journals=new HashSet<Journal>();
        private static readonly FieldInfo JournalEnglishField=typeof(Journal).GetField(
            "objectivesDescriptionsENG",BindingFlags.Instance|BindingFlags.NonPublic);

        private void Awake()
        {
            int check=1;
            try
            {
                if (Application.unityVersion!=BuildIdentity.UnityVersion) throw new FormatException();
                check=2;
                if (FileDigest(Path.Combine(Application.dataPath,"Managed/Assembly-CSharp.dll"))!=BuildIdentity.AssemblySha256
                    || FileDigest(Path.Combine(Path.GetDirectoryName(Application.dataPath),"UnityPlayer.dll"))!=BuildIdentity.UnityPlayerSha256)
                    throw new FormatException();
                check=3;
                string path=Path.Combine(Path.GetDirectoryName(Info.Location),"translation.json");
                if (new FileInfo(path).Length>8*1024*1024) throw new FormatException();
                Payload payload=PayloadJson.Parse(File.ReadAllText(path,new UTF8Encoding(false,true)));
                core=new TranslationCore(payload,BuildIdentity.UnityVersion,BuildIdentity.AssemblySha256);
                check=4;
                active=this;
                harmony=new Harmony("org.unitytranslator.kryptafm");
                // Targets are compiled literals. Payload data cannot select methods or types.
                harmony.PatchAll(typeof(Plugin).Assembly);
                Logger.LogInfo("Krypta runtime ready; English TextAsset memory hooks enabled.");
            }
            catch (Exception) { Stop(check); }
        }

        private static string FileDigest(string path)
        {
            using(FileStream stream=File.OpenRead(path)) using(SHA256 hash=SHA256.Create())
            {
                StringBuilder result=new StringBuilder(64);
                foreach(byte value in hash.ComputeHash(stream)) result.Append(value.ToString("x2"));
                return result.ToString();
            }
        }

        private TextAsset Replace(TextAsset asset)
        {
            if(asset==null || originals.ContainsKey(asset) || !core.Contains(asset.name)) return asset;
            TextAsset replacement;
            if(replacements.TryGetValue(asset,out replacement)) return replacement;
            string text=core.Translate(asset.name,asset.text);
            replacement=new TextAsset(text); replacement.name=asset.name;
            replacements.Add(asset,replacement); originals.Add(replacement,asset);
            return replacement;
        }

        private List<TextAsset> ReplaceList(List<TextAsset> source)
        {
            if(source==null) return null;
            if(source.Count>256) throw new FormatException();
            List<TextAsset> result=new List<TextAsset>(source.Count);
            bool changed=false;
            foreach(TextAsset asset in source)
            { TextAsset replacement=Replace(asset); result.Add(replacement); if(replacement!=asset) changed=true; }
            return changed ? result : source;
        }

        private void RestoreList(List<TextAsset> list)
        {
            if(list==null) return;
            for(int i=0;i<list.Count;i++)
            { TextAsset original; if(list[i]!=null && originals.TryGetValue(list[i],out original)) list[i]=original; }
        }

        private static bool SameLines(string[] lines, string text)
        {
            if(lines==null) return false;
            string[] expected=text.Split(new char[]{'\n'},StringSplitOptions.None);
            if(lines.Length!=expected.Length) return false;
            for(int i=0;i<lines.Length;i++) if(lines[i]!=expected[i]) return false;
            return true;
        }

        private void RestoreSubtitleLines(SubtitlesManager manager)
        {
            foreach(KeyValuePair<TextAsset,TextAsset> pair in originals)
                if(SameLines(manager.currentSubtitlesString,pair.Key.text))
                {
                    manager.currentSubtitlesString=pair.Value.text.Split(new char[]{'\n'},StringSplitOptions.None);
                    return;
                }
        }

        private void Menu(TranslateManager manager)
        {
            if(stopped || manager==null || manager.isPolish) return;
            try
            {
                TextAsset original=manager.textAssetEng, replacement=Replace(original);
                if(original==replacement) return;
                undo.Add(delegate {
                    if(manager==null) return;
                    manager.textAssetEng=original;
                    if(SameLines(manager.currentTranslation,replacement.text))
                        manager.currentTranslation=original.text.Split(new char[]{'\n'},StringSplitOptions.None);
                });
                manager.textAssetEng=replacement;
                Logger.LogInfo("Krypta menu source verified and replaced in memory.");
            }
            catch(Exception) { Stop(10); }
        }

        private void Posts(PostInfoManager manager)
        {
            if(stopped || manager==null || manager.isPolish) return;
            try
            {
                List<TextAsset> posts=manager.postScriptsListENG, keys=manager.keyPostScriptsListENG,
                    messages=manager.messagesListENG;
                // Validate all lists before assigning any consumer field.
                List<TextAsset> nextPosts=ReplaceList(posts), nextKeys=ReplaceList(keys), nextMessages=ReplaceList(messages);
                if(posts==nextPosts && keys==nextKeys && messages==nextMessages) return;
                undo.Add(delegate {
                    if(manager==null) return;
                    manager.postScriptsListENG=posts; manager.keyPostScriptsListENG=keys; manager.messagesListENG=messages;
                    RestoreList(manager.currentPostScriptsList); RestoreList(manager.currentKeyPostScriptsList);
                    RestoreList(manager.currentMessagesList);
                });
                manager.postScriptsListENG=nextPosts; manager.keyPostScriptsListENG=nextKeys; manager.messagesListENG=nextMessages;
                Logger.LogInfo("Krypta forum/message sources verified and replaced in memory.");
            }
            catch(Exception) { Stop(11); }
        }

        private void Subtitles(SubtitlesManager manager)
        {
            if(stopped || manager==null || TranslateManager.instance==null || TranslateManager.instance.isPolish) return;
            try
            {
                List<TextAsset> original=manager.subtitlesListENG, next=ReplaceList(original);
                if(original==next) return;
                undo.Add(delegate {
                    if(manager==null) return;
                    RestoreSubtitleLines(manager);
                    manager.subtitlesListENG=original; RestoreList(manager.currentSubtitlesList);
                });
                manager.subtitlesListENG=next;
                Logger.LogInfo("Krypta subtitle sources verified and replaced in memory.");
            }
            catch(Exception) { Stop(12); }
        }

        private void SelectedSubtitles(SubtitlesManager manager)
        {
            if(stopped || manager==null || TranslateManager.instance==null || TranslateManager.instance.isPolish) return;
            try
            {
                List<TextAsset> previous=manager.currentSubtitlesList, next=ReplaceList(previous);
                if(previous==next) return;
                undo.Add(delegate {
                    if(manager==null) return;
                    RestoreSubtitleLines(manager);
                    RestoreList(previous);
                    manager.currentSubtitlesList=previous;
                });
                manager.currentSubtitlesList=next;
            }
            catch(Exception) { Stop(13); }
        }

        private void JournalText(Journal manager,ref string[,] values)
        {
            const string sourceName="Journal.objectivesDescriptionsENG";
            if(stopped || manager==null || journals.Contains(manager) || !core.Contains(sourceName)) return;
            try
            {
                if(JournalEnglishField==null || values==null || values.GetLength(0)!=4 || values.GetLength(1)!=3)
                    throw new FormatException();
                string[] originalCells=new string[12];
                for(int row=0;row<4;row++) for(int column=0;column<3;column++)
                {
                    string value=values[row,column];
                    if(value==null || value.IndexOfAny(new char[]{'\r','\n','\0'})>=0) throw new FormatException();
                    originalCells[row*3+column]=value;
                }
                string[] target=core.Translate(sourceName,String.Join("\n",originalCells)).Split('\n');
                if(target.Length!=12) throw new FormatException();
                string[,] original=values, replacement=(string[,])original.Clone();
                for(int row=0;row<4;row++) for(int column=0;column<3;column++)
                    replacement[row,column]=target[row*3+column];
                // The private field is a compiled literal, never selected by payload/profile data.
                undo.Add(delegate { if(manager!=null) JournalEnglishField.SetValue(manager,original); });
                journals.Add(manager);
                values=replacement;
                Logger.LogInfo("Krypta English journal objectives verified and replaced in memory.");
            }
            catch(Exception) { Stop(14); }
        }

        private void Stop(int check)
        {
            if(stopped) return;
            stopped=true;
            if(harmony!=null) { try { harmony.UnpatchSelf(); } catch(Exception) { } }
            for(int i=undo.Count-1;i>=0;i--) { try { undo[i](); } catch(Exception) { } }
            undo.Clear();
            journals.Clear();
            foreach(TextAsset asset in originals.Keys) if(asset!=null) UnityEngine.Object.Destroy(asset);
            originals.Clear(); replacements.Clear();
            Logger.LogError("Krypta runtime stopped at check "+check+"; no original game file was written.");
        }
        private void OnDestroy() { Stop(20); if(active==this) active=null; }

        [HarmonyPatch(typeof(TranslateManager),"LoadTranslationFile")]
        private static class MenuHook { private static void Prefix(TranslateManager __instance) { if(active!=null) active.Menu(__instance); } }
        [HarmonyPatch(typeof(PostInfoManager),"SetPostsLanguage")]
        private static class PostsHook { private static void Prefix(PostInfoManager __instance) { if(active!=null) active.Posts(__instance); } }
        [HarmonyPatch(typeof(SubtitlesManager),"SetSubsLanguage")]
        private static class SubtitlesHook { private static void Prefix(SubtitlesManager __instance) { if(active!=null) active.Subtitles(__instance); } }
        [HarmonyPatch(typeof(SubtitlesManager),"PrepareSubList")]
        private static class SelectedSubtitlesHook { private static void Prefix(SubtitlesManager __instance) { if(active!=null) active.SelectedSubtitles(__instance); } }
        [HarmonyPatch(typeof(Journal),"Start")]
        private static class JournalHook { private static void Prefix(Journal __instance,ref string[,] ___objectivesDescriptionsENG) { if(active!=null) active.JournalText(__instance,ref ___objectivesDescriptionsENG); } }
    }
}
