
const string Domain = "observatory-instrument";
const char Separator = ':';
const string FailureMode = "1";
const string OutputOrder = "ordinal ascending";

string input = await Console.In.ReadToEndAsync();
Console.WriteLine($"{Domain};{Separator};{FailureMode};{OutputOrder};{input.Length}");
Console.WriteLine("NOT_IMPLEMENTED");
