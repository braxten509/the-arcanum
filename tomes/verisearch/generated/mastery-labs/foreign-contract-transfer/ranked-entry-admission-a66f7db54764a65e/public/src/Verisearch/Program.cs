using System.Globalization;

const string Domain = "trail-checkpoint";
const char Separator = ';';
const string FailureMode = "2";
const string OutputOrder = "ordinal identifier ascending";

string input = await Console.In.ReadToEndAsync();
_ = RankingContract.Parse(input, Separator);
Console.WriteLine($"domain={Domain}; cap={FailureMode}; order={OutputOrder}; input={input.Length}");
Console.WriteLine("NOT_IMPLEMENTED");

internal sealed record RankedEntry(string Id, int Priority);

internal static class RankingContract
{
    internal static RankedEntry? Parse(string line, char separator) => null;
}
