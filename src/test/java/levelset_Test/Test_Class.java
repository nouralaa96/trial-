package levelset_Test;

import org.openqa.selenium.WebDriver;
import org.openqa.selenium.chrome.ChromeDriver;
import org.testng.Assert;
import org.testng.annotations.AfterClass;
import org.testng.annotations.BeforeClass;
import org.testng.annotations.Test;

import actions.BrowserActions;
import io.github.bonigarcia.wdm.WebDriverManager;
import levelset_Main.Create_Document_Page;
import levelset_Main.Levelset_HomePage;

public class Test_Class { 
	    WebDriver driver ;  
	      BrowserActions action ;
	    Levelset_HomePage homepage ; 
	    Create_Document_Page basicpage ;

	    @BeforeClass
	  public  WebDriver Setup() {
	        WebDriverManager.chromedriver().setup();
	  //      driver = new ChromeDriver() ;
	  //      driver.manage().window().maximize();   
	          action =  new BrowserActions() ;
	          driver = action.initializeWebdriver() ;  
	          homepage =new Levelset_HomePage() ; 
	             homepage.navigateLevelset() ;  
	             action.maximizeWindow(); 
	      //       basicpage= new Create_Document_Page(driver) ;
	                    return driver ;                   // for reuse of function in another test classes 
	      /*  homepage =new Levelset_HomePage(driver) ; 
	        basicpage= new Create_Document_Page(driver) ;*/
	          
		      
	        
	        }  
	  @AfterClass
	     public void aftermethod () { 
	    	action.closeDriver();
	    }   
 /*  @Test
  public void checknavigation() {
	  
	  //homepage.navigateLevelset() ;
	  
	  Assert.assertEquals(homepage.check_navigaton_bysearch(), "for Subs, Suppliers, and GC’s");
  }  */ 
  @Test
  public void check_create_a_document_isclickable() {
	   //Assert.assertTrue(homepage.checkclickable_create_a_document() );
	     homepage.checkclickable_create_a_document(); // only call the function .
  }
  @Test 
  public void validate20_DayPreliminaryNotice() { 
	    homepage.checkclickable_create_a_document() ;
	     
	    basicpage.vaildate_DayPreliminaryNotices("20-Day Preliminary Notice");
	   //  Assert.assertEquals(basicpage.get0_DayPreliminaryNoticestring("20-Day Preliminary Notice"), "Free");
	 //    Assert.assertEquals(basicpage.get0_DayPreliminaryNoticestringclick1(), "20-Day Preliminary Notice");
	    
  } 
  
  @Test 
  public void validateNoticeofIntenttoLien() { 
	  
	          homepage.checkclickable_create_a_document() ;
	     
	         basicpage.vaildate0_NoticeofIntenttoLien();
	     
	       // Assert.assertEquals(basicpage.get0_NoticeofIntenttoLien(), "Free");
	  
  } 
  @Test 
  public void validateNLienBondClaim() { 
	         
	     
	     Assert.assertEquals(basicpage.get0_NLienBondClaim(), "Free");
	  
  } 
  @Test 
  public void validateLienWaiver() { 
	         
	     
	     Assert.assertEquals(basicpage.get0_LienWaiver(), "Free");
	  
  } 
}
