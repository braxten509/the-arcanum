using System.Globalization;

const string Domain = "harbor-cargo";
const char Separator = '|';
const string FailureMode = "discard";
const string OutputOrder = "ascending";

string input = await Console.In.ReadToEndAsync();
_ = LedgerContract.Parse(input, Separator);
Console.WriteLine($"domain={Domain}; mode={FailureMode}; order={OutputOrder}; input={input.Length}");
Console.WriteLine("NOT_IMPLEMENTED");

internal sealed record LedgerRow(string Key, int Amount);

internal static class LedgerContract
{
    internal static LedgerRow? Parse(string line, char separator) => null;
}
