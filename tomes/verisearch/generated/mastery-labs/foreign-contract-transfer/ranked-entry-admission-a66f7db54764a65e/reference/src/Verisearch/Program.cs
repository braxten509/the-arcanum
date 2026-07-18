using System.Globalization;

const string Domain = "trail-checkpoint";
const char Separator = ';';
const string FailureMode = "2";
const string OutputOrder = "ordinal identifier ascending";

string input = await Console.In.ReadToEndAsync();
RankingResult result = RankingContract.Rank(input, Separator, FailureMode, OutputOrder);
Console.WriteLine($"domain={Domain}");
Console.WriteLine($"rejection-cap={FailureMode}");
Console.WriteLine($"order={OutputOrder}");
Console.WriteLine($"ids={string.Join(',', result.Ids)}");
Console.WriteLine($"accepted={result.Accepted}");
Console.WriteLine($"rejected={result.Rejected}");

internal sealed record RankedEntry(string Id, int Priority);
internal sealed record RankingResult(IReadOnlyList<string> Ids, int Accepted, int Rejected);

internal static class RankingContract
{
    internal static RankedEntry? Parse(string line, char separator)
    {
        string[] fields = line.TrimEnd('\r').Split(separator);
        return fields.Length == 2
            && IsIdentifier(fields[0])
            && IsUnsignedAsciiInt32(fields[1], out int priority)
            ? new RankedEntry(fields[0], priority)
            : null;
    }

    private static bool IsIdentifier(string text) =>
        text.Length is >= 1 and <= 16
        && text[0] is >= 'A' and <= 'Z'
        && text[1..].All(character => character is >= 'A' and <= 'Z'
                                            or >= '0' and <= '9' or '_');

    private static bool IsUnsignedAsciiInt32(string text, out int priority)
    {
        priority = 0;
        return text.Length > 0
            && text.All(character => character is >= '0' and <= '9')
            && int.TryParse(text, NumberStyles.None, CultureInfo.InvariantCulture, out priority);
    }

    internal static RankingResult Rank(
        string input, char separator, string failureMode, string outputOrder)
    {
        var entries = new List<RankedEntry>();
        int rejected = 0;
        foreach (string line in input.Split('\n', StringSplitOptions.RemoveEmptyEntries))
        {
            RankedEntry? entry = Parse(line, separator);
            if (entry is null)
            {
                rejected++;
                continue;
            }
            entries.Add(entry);
        }
        IEnumerable<RankedEntry> ordered = outputOrder.StartsWith("priority", StringComparison.Ordinal)
            ? entries.OrderByDescending(item => item.Priority).ThenBy(item => item.Id, StringComparer.Ordinal)
            : entries.OrderBy(item => item.Id, StringComparer.Ordinal);
        int cap = int.Parse(failureMode, NumberStyles.None, CultureInfo.InvariantCulture);
        return new RankingResult(ordered.Select(item => item.Id).ToArray(), entries.Count,
                                 Math.Min(rejected, cap));
    }
}
