using System;
using System.Globalization;
using System.Reflection;
using I2.Loc;

namespace UnityTranslator.I2Mono
{
    // Fixed, statically verified I2 fields; data cannot select reflection targets.
    public static class MemoryLanguage
    {
        private static readonly string[] Names = new string[] {
            "mCurrentLanguage", "mLanguageCode", "mCurrentCulture", "IsRight2Left", "HasJoinedWords"
        };
        private static readonly FieldInfo[] Fields = Resolve();
        private static readonly MethodInfo Localize = typeof(LocalizationManager).GetMethod(
            "DoLocalizeAll", BindingFlags.Static | BindingFlags.NonPublic, null, new Type[] { typeof(bool) }, null);
        private static FieldInfo[] Resolve()
        {
            FieldInfo[] fields = new FieldInfo[Names.Length];
            for (int i = 0; i < Names.Length; i++)
            {
                fields[i] = typeof(LocalizationManager).GetField(Names[i],
                    BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic);
                if (fields[i] == null) throw new InvalidOperationException("I2 language field missing.");
            }
            return fields;
        }
        public static object Capture()
        {
            if (Localize == null) throw new InvalidOperationException("I2 localization callback missing.");
            object[] values = new object[Fields.Length];
            for (int i = 0; i < values.Length; i++) values[i] = Fields[i].GetValue(null);
            return values;
        }
        public static void Select(string code, string name)
        {
            if (!TranslationCore.ValidLanguage(code)) throw new InvalidOperationException("Invalid language code.");
            CultureInfo culture;
            try { culture = new CultureInfo(code); }
            catch (ArgumentException) { culture = new CultureInfo(code.Split('-')[0]); }
            string primary = code.Split('-')[0].ToLowerInvariant();
            Fields[0].SetValue(null, name);
            Fields[1].SetValue(null, code);
            Fields[2].SetValue(null, culture);
            Fields[3].SetValue(null, culture.TextInfo.IsRightToLeft);
            Fields[4].SetValue(null, primary == "zh" || primary == "ja" || primary == "th");
        }
        public static void Restore(object snapshot)
        {
            object[] values = (object[])snapshot;
            for (int i = 0; i < values.Length; i++) Fields[i].SetValue(null, values[i]);
        }
        public static void Refresh()
        {
            Localize.Invoke(null, new object[] { true });
        }
    }
}
