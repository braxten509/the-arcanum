using System.Globalization;

const string Domain = "harbor-cargo";
const char Separator = '|';
const string FailureMode = "quarantine";
const string OutputOrder = "ascending";

string input = await Console.In.ReadToEndAsync();
LedgerResult result = LedgerContract.Reconcile(input, Separator, FailureMode, OutputOrder);
Console.WriteLine($"domain={Domain}");
Console.WriteLine($"policy={FailureMode}");
Console.WriteLine($"order={OutputOrder}");
Console.WriteLine($"entries={string.Join(',', result.Entries)}");
Console.WriteLine($"total={result.Total}");
Console.WriteLine($"invalid={result.InvalidStatus}");

internal sealed record LedgerRow(string Key, int Amount);
internal sealed record LedgerResult(IReadOnlyList<string> Entries, long Total, string InvalidStatus);

internal static class LedgerContract
{
    internal static LedgerRow? Parse(string line, char separator)
    {
        string[] fields = line.TrimEnd('\r').Split(separator);
        return fields.Length == 2
            && IsIdentifier(fields[0])
            && IsUnsignedAsciiInt32(fields[1], out int amount)
            ? new LedgerRow(fields[0], amount)
            : null;
    }

    private static bool IsIdentifier(string text) =>
        text.Length is >= 1 and <= 16
        && text[0] is >= 'A' and <= 'Z'
        && text[1..].All(character => character is >= 'A' and <= 'Z'
                                            or >= '0' and <= '9' or '_');

    private static bool IsUnsignedAsciiInt32(string text, out int amount)
    {
        amount = 0;
        return text.Length > 0
            && text.All(character => character is >= '0' and <= '9')
            && int.TryParse(text, NumberStyles.None, CultureInfo.InvariantCulture, out amount);
    }

    internal static LedgerResult Reconcile(
        string input, char separator, string failureMode, string outputOrder)
    {
        var totals = new Dictionary<string, long>(StringComparer.Ordinal);
        bool malformed = false;
        foreach (string line in input.Split('\n', StringSplitOptions.RemoveEmptyEntries))
        {
            LedgerRow? row = Parse(line, separator);
            if (row is null)
            {
                malformed = true;
                continue;
            }
            totals[row.Key] = checked(totals.GetValueOrDefault(row.Key) + row.Amount);
        }
        IEnumerable<KeyValuePair<string, long>> ordered = outputOrder == "ascending"
            ? totals.OrderBy(item => item.Key, StringComparer.Ordinal)
            : totals.OrderByDescending(item => item.Key, StringComparer.Ordinal);
        string[] entries = ordered.Select(item => $"{item.Key}:{item.Value}").ToArray();
        string invalidStatus = malformed ? failureMode : "none";
        long total = totals.Values.Aggregate(0L, (sum, value) => checked(sum + value));
        return new LedgerResult(entries, total, invalidStatus);
    }
}
