# 라디오 방송사 로고

`frontend/public/radio-logos/*.png`(`scripts/fetch_radio_logos.py`로 만듦)는 위키백과·위키미디어 공용의 로고 파일을 받아
흰 3:2 타일(288×192)에 맞춰 만든 것이다. 방송국마다 어떤 로고를 쓰는지는
`backend/app/radio_stations.json`의 `logo` 필드에 있다(없으면 방송사 약칭 배지).

- 지역 방송국은 같은 계열의 로고를 쓴다(예: 부산MBC 표준FM → MBC RADIO).
  MBC 표준FM·FM4U, SBS 러브FM·파워FM 채널 로고에는 서울 주파수가 적혀 있어 서울 방송에만 쓴다.
- 로고를 찾지 못했거나 다른 회사 것이 나와 뺀 곳: TBN, WBS(원음방송), 국악방송, 국방FM,
  부산영어방송, 글로벌광주방송, 공동체 라디오.

| 파일 | 원본 | 라이선스 | 출처 |
|---|---|---|---|
| `afn.png` | American Forces Network logo.png | Public domain | https://commons.wikimedia.org/wiki/File:American_Forces_Network_logo.png |
| `arirang.png` | Arirang.svg | Public domain | https://commons.wikimedia.org/wiki/File:Arirang.svg |
| `bbs.png` | Buddhist Broadcasting System logo.png | Public domain | https://commons.wikimedia.org/wiki/File:Buddhist_Broadcasting_System_logo.png |
| `cbs.png` | Christian Broadcasting System logo.svg | Public domain | https://commons.wikimedia.org/wiki/File:Christian_Broadcasting_System_logo.svg |
| `cjb.png` | Cjb logo.svg | Public domain | https://commons.wikimedia.org/wiki/File:Cjb_logo.svg |
| `cpbc.png` | CPBC logo.png | Public domain | https://commons.wikimedia.org/wiki/File:CPBC_logo.png |
| `ebs.png` | EBS Logo.svg | Public domain | https://commons.wikimedia.org/wiki/File:EBS_Logo.svg |
| `febc.png` | Febc logov2.gif | CC BY 3.0 | https://commons.wikimedia.org/wiki/File:Febc_logov2.gif |
| `g1.png` | G1 broadcasting logo.svg | Public domain | https://commons.wikimedia.org/wiki/File:G1_broadcasting_logo.svg |
| `ifm.png` | ITV LOGO.svg | CC BY-SA 4.0 | https://commons.wikimedia.org/wiki/File:ITV_LOGO.svg |
| `jtv.png` | JTV로고1.gif | CC BY-SA 4.0 | https://commons.wikimedia.org/wiki/File:JTV%EB%A1%9C%EA%B3%A01.gif |
| `kbc.png` | Kbc logo2.svg | Public domain | https://commons.wikimedia.org/wiki/File:Kbc_logo2.svg |
| `kbs.png` | KBS logo (2001).svg | Public domain | https://commons.wikimedia.org/wiki/File:KBS_logo_(2001).svg |
| `kbs-1radio.png` | KBS Radio 1 logo.svg | Public domain | https://commons.wikimedia.org/wiki/File:KBS_Radio_1_logo.svg |
| `kbs-2fm.png` | KBS2FM logo.svg | Public domain | https://commons.wikimedia.org/wiki/File:KBS2FM_logo.svg |
| `knn.png` | KNN logo.svg | Public domain | https://commons.wikimedia.org/wiki/File:KNN_logo.svg |
| `mbc.png` | MBC Radio 2018.svg | Public domain | https://commons.wikimedia.org/wiki/File:MBC_Radio_2018.svg |
| `mbc-fm4u.png` | MBC FM4U Logo.svg | CC BY-SA 2.5 | https://commons.wikimedia.org/wiki/File:MBC_FM4U_Logo.svg |
| `mbc-sfm.png` | MBC Standard FM Logo.svg | CC BY-SA 2.5 | https://commons.wikimedia.org/wiki/File:MBC_Standard_FM_Logo.svg |
| `obs.png` | OBS Kyung-In TV 2023.png | CC BY 4.0 | https://commons.wikimedia.org/wiki/File:OBS_Kyung-In_TV_2023.png |
| `sbs.png` | Seoul Broadcasting System logo.svg | Public domain | https://commons.wikimedia.org/wiki/File:Seoul_Broadcasting_System_logo.svg |
| `sbs-love.png` | SBS Love FM Logo.svg | CC BY-SA 2.5 | https://commons.wikimedia.org/wiki/File:SBS_Love_FM_Logo.svg |
| `sbs-power.png` | SBS Power FM Logo.svg | CC BY-SA 2.5 | https://commons.wikimedia.org/wiki/File:SBS_Power_FM_Logo.svg |
| `tbc.png` | Daegu Broadcasting Corporation.svg | Public domain | https://commons.wikimedia.org/wiki/File:Daegu_Broadcasting_Corporation.svg |
| `tbs.png` | Traffic Broadcasting System logo.png | Public domain | https://commons.wikimedia.org/wiki/File:Traffic_Broadcasting_System_logo.png |
| `tjb.png` | Tjb logo.svg | Public domain | https://commons.wikimedia.org/wiki/File:Tjb_logo.svg |
| `ubc.png` | UBC 울산방송.svg | Public domain | https://commons.wikimedia.org/wiki/File:UBC_%EC%9A%B8%EC%82%B0%EB%B0%A9%EC%86%A1.svg |
| `ytn.png` | YTN logo 2014.svg | Public domain | https://commons.wikimedia.org/wiki/File:YTN_logo_2014.svg |

로고의 상표권은 각 방송사에 있다.
