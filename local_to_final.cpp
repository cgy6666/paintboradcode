#include<bits/stdc++.h>
using namespace std;
string s1 , s2;
int main()
{
	freopen("access_local.txt" , "r" , stdin);
	freopen("access_final.txt" , "w" , stdout);
	ios::sync_with_stdio(0);
	ios_base::sync_with_stdio(0);
	cin.tie(0);
	cout.tie(0);
	cout << "ACCESS_KEYS = [\n    # 格式：{\"uid\": 用户ID, \"access_key\": \"访问密钥\"}\n    # 可以从洛谷绘版获取 access key ";
	while(cin >> s1 >> s2)
	{
		cout << ",\n    {\"uid\": " << s1 << ", \"access_key\": \"" << s2 << "\"\}";
	}
	cout << "\n    # 可以继续添加更多 access key，最多建议70个\n]";
	return 0;
}
