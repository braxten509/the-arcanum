using System.Globalization;

const string Domain = "observatory-instrument";
const char Separator = ':';
const string FailureMode = "0";
const string OutputOrder = "ordinal descending";

string input = await Console.In.ReadToEndAsync();
CommandResult result = CommandContract.Apply(input, Separator, FailureMode, OutputOrder);
Console.WriteLine($"domain={Domain}");
Console.WriteLine($"mode={FailureMode}");
Console.WriteLine($"order={OutputOrder}");
Console.WriteLine($"keys={string.Join(',', result.Keys)}");
Console.WriteLine($"total={result.Total}");
Console.WriteLine($"invalid={result.InvalidObservation}");

internal sealed record StateCommand(string Key, int Value);
internal sealed record CommandResult(IReadOnlyList<string> Keys, long Total, int InvalidObservation);

internal static class CommandContract
{
    internal static StateCommand? Parse(string line, char separator)
    {
        string[] fields = line.TrimEnd('\r').Split(separator);
        return fields.Length == 3
            && fields[0] == "SET"
            && IsIdentifier(fields[1])
            && IsSignedAsciiInt32(fields[2], out int value)
            ? new StateCommand(fields[1], value)
            : null;
    }

    private static bool IsIdentifier(string text) =>
        text.Length is >= 1 and <= 16
        && text[0] is >= 'a' and <= 'z'
        && text[1..].All(character => character is >= 'a' and <= 'z'
                                            or >= '0' and <= '9' or '_');

    private static bool IsSignedAsciiInt32(string text, out int value)
    {
        value = 0;
        int firstDigit = text.StartsWith('+') || text.StartsWith('-') ? 1 : 0;
        bool lexicalMatch = firstDigit < text.Length
            && text[firstDigit..].All(character => character is >= '0' and <= '9');
        return lexicalMatch
            && int.TryParse(text, NumberStyles.AllowLeadingSign,
                            CultureInfo.InvariantCulture, out value);
    }

    internal static CommandResult Apply(
        string input, char separator, string failureMode, string outputOrder)
    {
        var state = new Dictionary<string, int>(StringComparer.Ordinal);
        int malformed = 0;
        foreach (string line in input.Split('\n', StringSplitOptions.RemoveEmptyEntries))
        {
            StateCommand? command = Parse(line, separator);
            if (command is null)
            {
                malformed++;
                continue;
            }
            state[command.Key] = command.Value;
        }
        IEnumerable<string> ordered = outputOrder == "ordinal ascending"
            ? state.Keys.Order(StringComparer.Ordinal)
            : state.Keys.OrderDescending(StringComparer.Ordinal);
        int observation = failureMode == "1" ? malformed : 0;
        long total = state.Values.Aggregate(0L, (sum, value) => checked(sum + value));
        return new CommandResult(ordered.ToArray(), total, observation);
    }
}
