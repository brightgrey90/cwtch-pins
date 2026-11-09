# New Etsy listings to Pinterest

Every 3 hours this checks the shop through Etsy's official API and adds new listings to `feed/new-listings.xml`.
Zapier watches that feed and creates a pin for each new item.

The first run only records existing listings, so nothing already listed gets pinned again.

Needs one repository secret, `ETSY_API_KEY`, in the form `keystring:sharedsecret`.
